"""Config and options flow for Summit Control."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SummitControlAuthError,
    SummitControlClient,
    SummitControlConnectionError,
    SummitControlError,
)
from .const import (
    COMMAND_MODES,
    CONF_COMMAND_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MODE_AUTO,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


async def _validate_credentials(hass, username: str, password: str) -> None:
    """Raise on bad credentials or connectivity; return None on success."""
    client = SummitControlClient(async_get_clientsession(hass), username, password)
    await client.async_login()
    # Prove the token works against a real read.
    await client.async_get_devices()


class SummitControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup flow."""

    VERSION = 1
    _reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            errors = await self._try_validate(username, user_input[CONF_PASSWORD])
            if not errors:
                return self.async_create_entry(
                    title=username,
                    data={CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._reauth_entry
        if user_input is not None:
            username = reauth_entry.data[CONF_USERNAME]
            errors = await self._try_validate(username, user_input[CONF_PASSWORD])
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={
                CONF_USERNAME: reauth_entry.data[CONF_USERNAME]
            },
        )

    async def _try_validate(self, username: str, password: str) -> dict[str, str]:
        try:
            await _validate_credentials(self.hass, username, password)
        except SummitControlAuthError:
            return {"base": "invalid_auth"}
        except SummitControlConnectionError:
            return {"base": "cannot_connect"}
        except SummitControlError:
            return {"base": "unknown"}
        except Exception:  # noqa: BLE001 - surface as generic error, don't crash the flow
            _LOGGER.exception("Unexpected error validating Summit Control credentials")
            return {"base": "unknown"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SummitControlOptionsFlow()


class SummitControlOptionsFlow(OptionsFlow):
    """Poll interval + command-mode override."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_COMMAND_MODE,
                    default=options.get(CONF_COMMAND_MODE, MODE_AUTO),
                ): vol.In(COMMAND_MODES),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
