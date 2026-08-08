"""Async client for the Summit Control "Sierra" cloud API.

Reverse-engineered from the Sierra web app + `com.summitcontrol` phone app and
confirmed live. Flow:

  1. POST  {IDENTITY_BASE}/login            {username, password}
        -> {message: {user, access_token, refresh_token}} (+ auth cookies).
           The access_token is a short-lived (~120 s) JWT.
  2. GET   {IDENTITY_BASE}/refresh-token     (uses the refresh cookie) -> new token.
  3. Authenticated REST calls to {API_BASE}/v1/... carry an `access_token: <jwt>`
     HTTP header (NOT `Authorization: Bearer`).
  4. Discover the gates a *resident* may open:
        POST /v1/shell/get_by_user           {user_id}      -> user_group_id(s)
        POST /v1/user_group_permission/get/all {user_group_id} -> device_id + relay
                                                                  resource_ids + actions
        POST /v1/device/get/ids              {device_ids}   -> device names
        POST /v1/device_resource/get/all_by_ids {resource_ids} -> relay names
  5. Open a gate:
        POST /v1/command/open                {device, resource, user}

A dedicated aiohttp session with its own cookie jar is used (not HA's shared
session) because the refresh flow relies on the identity cookies.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    DEFAULT_TOKEN_TTL,
    EP_COMMAND,
    EP_DEVICES_BY_IDS,
    EP_GROUP_PERMISSIONS,
    EP_RESOURCES_BY_IDS,
    EP_SHELL_BY_USER,
    IDENTITY_BASE,
    REQUEST_TIMEOUT,
    TOKEN_REFRESH_MARGIN,
)

_LOGGER = logging.getLogger(__name__)


class SummitError(Exception):
    """Base error."""


class SummitAuthError(SummitError):
    """Invalid credentials or unrecoverable auth failure."""


class SummitConnectionError(SummitError):
    """Network/transport problem talking to the Sierra cloud."""


@dataclass(frozen=True)
class Gate:
    """One openable relay resource on a device the user has access to."""

    device_id: str
    resource_id: str
    name: str
    device_name: str
    device_type: str

    @property
    def unique_id(self) -> str:
        return f"{self.device_id}_{self.resource_id}"


def _jwt_expiry(token: str) -> float | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except (IndexError, ValueError, binascii.Error, TypeError):
        return None


class SummitClient:
    """Talks to the Summit Control Sierra identity + REST API."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._user_id: str | None = None

    # -------------------------------------------------------------- session
    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            )
        return self._session

    async def async_close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # ----------------------------------------------------------------- auth
    async def async_login(self) -> dict[str, Any]:
        """Authenticate; returns the user object. Raises on bad credentials."""
        session = self._get_session()
        try:
            async with session.post(
                f"{IDENTITY_BASE}/login",
                json={"username": self._username, "password": self._password},
            ) as resp:
                body = await resp.text()
                if resp.status in (400, 401, 403):
                    raise SummitAuthError(f"Login rejected (HTTP {resp.status})")
                if resp.status >= 400:
                    raise SummitError(f"Login failed (HTTP {resp.status}): {body[:200]}")
                data = _loads(body)
        except aiohttp.ClientError as err:
            raise SummitConnectionError(str(err)) from err

        message = (data or {}).get("message") or {}
        token = message.get("access_token")
        user = message.get("user") or {}
        if not token or not user.get("_id"):
            raise SummitAuthError("Login response missing access_token/user")
        self._set_token(token)
        self._user_id = user["_id"]
        return user

    async def async_refresh(self) -> None:
        """Renew the access token; fall back to a full re-login."""
        session = self._get_session()
        try:
            async with session.get(f"{IDENTITY_BASE}/refresh-token") as resp:
                if resp.status == 200:
                    data = _loads(await resp.text()) or {}
                    token = (data.get("message") or {}).get("access_token") or data.get("access_token")
                    if token:
                        self._set_token(token)
                        return
        except aiohttp.ClientError as err:
            _LOGGER.debug("refresh-token failed (%s); re-logging in", err)
        await self.async_login()

    def _set_token(self, token: str) -> None:
        self._access_token = token
        exp = _jwt_expiry(token)
        self._token_expiry = exp if exp is not None else time.time() + DEFAULT_TOKEN_TTL

    async def _ensure_token(self) -> None:
        if self._access_token is None or self._user_id is None:
            await self.async_login()
        elif time.time() >= self._token_expiry - TOKEN_REFRESH_MARGIN:
            await self.async_refresh()

    # -------------------------------------------------------------- requests
    async def _api(self, method: str, path: str, json_body: Any | None = None) -> Any:
        await self._ensure_token()
        status, body = await self._raw(method, path, json_body)
        if status == 401:
            await self.async_refresh()
            status, body = await self._raw(method, path, json_body)
        if status == 401:
            raise SummitAuthError(f"Unauthorized on {path}")
        if status >= 400:
            raise SummitError(f"HTTP {status} on {path}: {body[:200]}")
        return _loads(body)

    async def _raw(self, method: str, path: str, json_body: Any | None) -> tuple[int, str]:
        session = self._get_session()
        headers = {"access_token": self._access_token or "", "Accept": "application/json"}
        try:
            async with session.request(
                method, f"{API_BASE}{path}", json=json_body, headers=headers
            ) as resp:
                return resp.status, await resp.text()
        except aiohttp.ClientError as err:
            raise SummitConnectionError(str(err)) from err

    # ------------------------------------------------------------ discovery
    async def async_discover_gates(self) -> list[Gate]:
        """Return the gates (relay resources) this user is allowed to open."""
        await self._ensure_token()
        assert self._user_id is not None

        shells = await self._api("POST", EP_SHELL_BY_USER, {"user_id": self._user_id})
        group_ids = {
            s.get("user_group_id")
            for s in _as_list(shells)
            if s.get("user_group_id")
        }

        # Collect (device_id, resource_id) pairs the user may open.
        pairs: list[tuple[str, str]] = []
        for gid in group_ids:
            perms = await self._api("POST", EP_GROUP_PERMISSIONS, {"user_group_id": gid})
            for perm in _as_list(perms):
                device_id = perm.get("device_id")
                actions = perm.get("actions") or {}
                if not device_id or not actions.get("open"):
                    continue
                for relay in perm.get("relays") or []:
                    rid = relay.get("resource_id") if isinstance(relay, dict) else None
                    if rid:
                        pairs.append((device_id, rid))

        # Dedupe while preserving order.
        seen: set[tuple[str, str]] = set()
        pairs = [p for p in pairs if not (p in seen or seen.add(p))]
        if not pairs:
            return []

        device_ids = list({d for d, _ in pairs})
        resource_ids = [r for _, r in pairs]
        devices = _index(await self._api("POST", EP_DEVICES_BY_IDS, {"device_ids": device_ids}))
        resources = _index(await self._api("POST", EP_RESOURCES_BY_IDS, {"resource_ids": resource_ids}))

        gates: list[Gate] = []
        for device_id, resource_id in pairs:
            dev = devices.get(device_id, {})
            res = resources.get(resource_id, {})
            gates.append(
                Gate(
                    device_id=device_id,
                    resource_id=resource_id,
                    name=res.get("name") or "Gate",
                    device_name=dev.get("name") or "Summit Control",
                    device_type=dev.get("type") or "",
                )
            )
        return gates

    # ------------------------------------------------------------- commands
    async def async_open_gate(self, device_id: str, resource_id: str) -> None:
        """Fire the momentary open relay for one gate."""
        await self._ensure_token()
        payload = {"device": device_id, "resource": resource_id, "user": self._user_id}
        data = await self._api("POST", f"{EP_COMMAND}open", payload)
        if isinstance(data, dict) and data.get("error"):
            raise SummitError(f"open command rejected: {data.get('message')}")


def _loads(body: str) -> Any:
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _index(data: Any) -> dict[str, dict[str, Any]]:
    """Index a list of {_id: ...} objects by their _id."""
    out: dict[str, dict[str, Any]] = {}
    for item in _as_list(data):
        if item.get("_id"):
            out[item["_id"]] = item
    return out
