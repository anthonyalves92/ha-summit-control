"""DataUpdateCoordinator for Summit Control."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SummitControlAuthError, SummitControlClient, SummitControlError, canonical_device_id
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SummitControlCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls user/dashboard and exposes devices keyed by canonical deviceID."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SummitControlClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            devices = await self.client.async_get_devices()
        except SummitControlAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SummitControlError as err:
            raise UpdateFailed(str(err)) from err

        result: dict[str, dict[str, Any]] = {}
        for detail in devices:
            device_id = canonical_device_id(detail)
            if device_id:
                result[device_id] = detail
        return result
