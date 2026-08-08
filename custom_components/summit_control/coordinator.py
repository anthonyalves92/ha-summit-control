"""DataUpdateCoordinator for Summit Control (Sierra)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Gate, SummitAuthError, SummitClient, SummitError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SummitCoordinator(DataUpdateCoordinator[dict[str, Gate]]):
    """Discovers the gates a user may open, keyed by gate unique_id.

    There is no live open/closed state for a resident (momentary open only), so
    polling mainly re-discovers gates and keeps the short-lived token refreshed.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SummitClient,
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

    async def _async_update_data(self) -> dict[str, Gate]:
        try:
            gates = await self.client.async_discover_gates()
        except SummitAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SummitError as err:
            raise UpdateFailed(str(err)) from err
        return {gate.unique_id: gate for gate in gates}
