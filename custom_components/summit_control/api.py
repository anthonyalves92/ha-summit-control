"""Async client for the Summit Control (Security Brands SnapApi) cloud."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    EP_ACTIONS_OPEN,
    EP_DASHBOARD,
    EP_LATCH_CLOSE,
    EP_LATCH_OPEN,
    EP_LOGIN,
    EP_RELAY_STATUS,
    GRANT_TYPE,
    REQUEST_TIMEOUT,
    TOKEN_EXPIRY_MARGIN,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

_JSON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Content-Type": "application/json;charset=UTF-8",
}


class SummitControlError(Exception):
    """Base error."""


class SummitControlAuthError(SummitControlError):
    """Invalid credentials or rejected token."""


class SummitControlConnectionError(SummitControlError):
    """Network/transport problem talking to the cloud."""


def canonical_device_id(detail: dict[str, Any]) -> str | None:
    """Return the identifier the API commands expect (deviceID), with fallbacks."""
    return detail.get("deviceID") or detail.get("ID") or None


def canonical_device_code(detail: dict[str, Any]) -> str | None:
    """Return the device code the API commands expect (deviceCode), with fallbacks."""
    return detail.get("deviceCode") or detail.get("device_code") or None


class SummitControlClient:
    """Talks to https://summitcontrol.com/SnapApi/index.php/.

    Auth is OAuth2 ``client_credentials`` (username -> client_id, password ->
    client_secret). The server issues only access tokens (no refresh token), so
    renewal is simply logging in again with the stored credentials.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_expiry: float = 0.0  # time.monotonic() deadline

    # ------------------------------------------------------------------ auth
    async def async_login(self) -> None:
        """Obtain a fresh access token."""
        payload = {
            "client_id": self._username,
            "client_secret": self._password,
            "grant_type": GRANT_TYPE,
        }
        status, body = await self._raw_request(
            "POST", EP_LOGIN, data=json.dumps(payload), authed=False
        )
        data = _safe_json(body)
        if status == 200 and data and data.get("access_token"):
            self._token = data["access_token"]
            expires_in = _as_int(data.get("expires_in"), default=3600)
            self._token_expiry = time.monotonic() + max(
                0, expires_in - TOKEN_EXPIRY_MARGIN
            )
            _LOGGER.debug("Summit Control login OK (expires_in=%s)", expires_in)
            return

        # OAuth2 / SnapApi error envelope
        detail = ""
        if data:
            detail = data.get("error_description") or data.get("message") or data.get("error") or ""
        raise SummitControlAuthError(
            f"Login failed (HTTP {status}){f': {detail}' if detail else ''}"
        )

    async def _async_ensure_token(self) -> None:
        if self._token is None or time.monotonic() >= self._token_expiry:
            await self.async_login()

    # --------------------------------------------------------------- reads
    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return a flat list of device-detail dicts from user/dashboard.

        Each dict is the raw ``DeviceDetail`` augmented with ``_address``.
        """
        data = await self._request_json("GET", EP_DASHBOARD)
        devices: list[dict[str, Any]] = []
        for group in (data.get("data") or {}).get("devices") or []:
            address = group.get("address")
            for detail in group.get("deviceDetails") or []:
                if isinstance(detail, dict):
                    detail = {**detail, "_address": address}
                    devices.append(detail)
        return devices

    async def async_relay_status(self, device_id: str, device_code: str) -> None:
        """Ask the unit to report fresh status (best-effort nudge)."""
        payload = {"deviceID": device_id, "deviceCode": device_code}
        try:
            await self._request_json("POST", EP_RELAY_STATUS, data=json.dumps(payload))
        except SummitControlError as err:  # non-fatal
            _LOGGER.debug("RelayStatus nudge failed: %s", err)

    # ------------------------------------------------------------- commands
    async def async_actions_open(
        self, device_id: str, device_code: str, relay: str
    ) -> None:
        """Momentary pulse (Actions/Open)."""
        await self._command(EP_ACTIONS_OPEN, device_id, device_code, relay)

    async def async_latch_open(
        self, device_id: str, device_code: str, relay: str
    ) -> None:
        """Maintained relay ON (Latch/Open)."""
        await self._command(EP_LATCH_OPEN, device_id, device_code, relay)

    async def async_latch_close(
        self, device_id: str, device_code: str, relay: str
    ) -> None:
        """Maintained relay OFF (Latch/Close)."""
        await self._command(EP_LATCH_CLOSE, device_id, device_code, relay)

    async def _command(
        self, endpoint: str, device_id: str, device_code: str, relay: str
    ) -> None:
        payload = {"deviceID": device_id, "deviceCode": device_code, "relay": str(relay)}
        data = await self._request_json("POST", endpoint, data=json.dumps(payload))
        # SnapApi returns {"status": int, "message": str}; treat 4xx status as error.
        status_field = data.get("status")
        if isinstance(status_field, int) and status_field >= 400:
            raise SummitControlError(
                f"{endpoint} rejected: {data.get('message') or status_field}"
            )

    # --------------------------------------------------------------- plumbing
    async def _request_json(
        self, method: str, endpoint: str, data: str | None = None
    ) -> dict[str, Any]:
        """Authed request that returns a parsed JSON object, retrying once on 401."""
        await self._async_ensure_token()
        status, body = await self._raw_request(method, endpoint, data=data, authed=True)
        if status == 401:
            _LOGGER.debug("401 on %s; re-authenticating and retrying once", endpoint)
            self._token = None
            await self.async_login()
            status, body = await self._raw_request(method, endpoint, data=data, authed=True)
        if status == 401:
            raise SummitControlAuthError(f"Unauthorized on {endpoint}")
        if status >= 400:
            raise SummitControlError(f"HTTP {status} on {endpoint}: {body[:200]}")
        parsed = _safe_json(body)
        if parsed is None:
            raise SummitControlError(f"Non-JSON response on {endpoint}: {body[:200]}")
        return parsed

    async def _raw_request(
        self,
        method: str,
        endpoint: str,
        data: str | None = None,
        authed: bool = True,
    ) -> tuple[int, str]:
        headers = dict(_JSON_HEADERS)
        if authed and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        url = BASE_URL + endpoint
        try:
            async with self._session.request(
                method,
                url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                text = await resp.text()
                return resp.status, text
        except aiohttp.ClientError as err:
            raise SummitControlConnectionError(str(err)) from err
        except TimeoutError as err:
            raise SummitControlConnectionError(f"Timeout contacting {url}") from err


def _safe_json(body: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
