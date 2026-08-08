"""Cover platform for Summit Control gates/relays."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SummitControlError, canonical_device_code
from .const import (
    CONF_COMMAND_MODE,
    DOMAIN,
    MODE_AUTO,
    MODE_LATCH,
    MODE_MOMENTARY,
    RELAY_CLOSED_VALUES,
    RELAY_OPEN_VALUES,
)
from .coordinator import SummitControlCoordinator

_LOGGER = logging.getLogger(__name__)


def _relay2_present(detail: dict[str, Any]) -> bool:
    value = detail.get("relay2_status") or detail.get("relay_2_status")
    return value not in (None, "", "null")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one cover per relay on each device from the first dashboard fetch."""
    coordinator: SummitControlCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SummitControlCover] = []
    for device_id, detail in coordinator.data.items():
        entities.append(SummitControlCover(coordinator, entry, device_id, "1"))
        if _relay2_present(detail):
            entities.append(SummitControlCover(coordinator, entry, device_id, "2"))
    async_add_entities(entities)


class SummitControlCover(CoordinatorEntity[SummitControlCoordinator], CoverEntity):
    """A single relay on a Summit Control unit, modeled as a gate cover."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: SummitControlCoordinator,
        entry: ConfigEntry,
        device_id: str,
        relay: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_id = device_id
        self._relay = relay
        self._attr_unique_id = f"{device_id}_relay{relay}"
        self._attr_name = None if relay == "1" else f"Relay {relay}"
        self._optimistic_closed: bool | None = None

    # --------------------------------------------------------------- data
    @property
    def _detail(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._device_id) or {}

    @property
    def _device_code(self) -> str:
        return canonical_device_code(self._detail) or ""

    def _relay_status_raw(self) -> str | None:
        if self._relay == "1":
            return self._detail.get("relay1_status")
        return self._detail.get("relay2_status") or self._detail.get("relay_2_status")

    def _reported_closed(self) -> bool | None:
        """True/False from the reported relay status, or None if unknown."""
        value = self._relay_status_raw()
        if value is None:
            return None
        token = str(value).strip().lower()
        if token in RELAY_CLOSED_VALUES:
            return True
        if token in RELAY_OPEN_VALUES:
            return False
        return None

    @property
    def _effective_mode(self) -> str:
        configured = self._entry.options.get(CONF_COMMAND_MODE, MODE_AUTO)
        if configured != MODE_AUTO:
            return configured
        # Auto: if the unit reports a usable relay state, treat it as a maintained latch.
        return MODE_LATCH if self._reported_closed() is not None else MODE_MOMENTARY

    # ------------------------------------------------------------- HA props
    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    @property
    def assumed_state(self) -> bool:
        return self._effective_mode == MODE_MOMENTARY

    @property
    def is_closed(self) -> bool | None:
        if self._effective_mode == MODE_LATCH:
            return self._reported_closed()
        return self._optimistic_closed

    @property
    def device_info(self) -> DeviceInfo:
        detail = self._detail
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Security Brands, Inc.",
            model=detail.get("product_name"),
            name=detail.get("location_name") or detail.get("_address") or detail.get("product_name") or "Summit Control gate",
            serial_number=detail.get("product_serial"),
        )

    # ------------------------------------------------------------- commands
    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._actuate(opening=True)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._actuate(opening=False)

    async def _actuate(self, opening: bool) -> None:
        client = self.coordinator.client
        code = self._device_code
        if not code:
            _LOGGER.warning(
                "Summit Control device %s has no deviceCode; sending command with empty code",
                self._device_id,
            )
        try:
            if self._effective_mode == MODE_LATCH:
                if opening:
                    await client.async_latch_open(self._device_id, code, self._relay)
                else:
                    await client.async_latch_close(self._device_id, code, self._relay)
            else:
                # Momentary: the operator has a single control line, so open and close
                # both fire the same Actions/Open pulse. State is optimistic.
                await client.async_actions_open(self._device_id, code, self._relay)
                self._optimistic_closed = not opening
                self.async_write_ha_state()
        except SummitControlError as err:
            raise HomeAssistantError(
                f"Summit Control command failed: {err}"
            ) from err

        # Pull fresh state (latch mode reflects the new relay status once the unit checks in).
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        # A real reported state supersedes any optimistic guess.
        if self._effective_mode == MODE_LATCH:
            self._optimistic_closed = None
        super()._handle_coordinator_update()
