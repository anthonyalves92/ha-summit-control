"""Cover platform for Summit Control (Sierra) gates."""
from __future__ import annotations

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

from .api import Gate, SummitError
from .const import DOMAIN, MANUFACTURER
from .coordinator import SummitCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one cover per openable gate relay."""
    coordinator: SummitCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [
            SummitGateCover(coordinator, uid)
            for uid in coordinator.data
            if uid not in known
        ]
        if new:
            known.update(g.unique_id for g in coordinator.data.values())
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class SummitGateCover(CoordinatorEntity[SummitCoordinator], CoverEntity):
    """A community gate the resident can momentarily open.

    Residents get an open-only, momentary command with no live position feedback,
    so the entity is assumed-state and advertises OPEN only.
    """

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = CoverEntityFeature.OPEN
    _attr_assumed_state = True

    def __init__(self, coordinator: SummitCoordinator, unique_id: str) -> None:
        super().__init__(coordinator)
        self._gate_uid = unique_id
        self._attr_unique_id = unique_id
        self._attr_name = self._gate.name

    @property
    def _gate(self) -> Gate:
        return self.coordinator.data[self._gate_uid]

    @property
    def available(self) -> bool:
        return super().available and self._gate_uid in self.coordinator.data

    @property
    def is_closed(self) -> bool | None:
        # No live position feedback for a resident; state is unknown/assumed.
        return None

    @property
    def device_info(self) -> DeviceInfo:
        gate = self._gate
        return DeviceInfo(
            identifiers={(DOMAIN, gate.device_id)},
            manufacturer=MANUFACTURER,
            model=gate.device_type or None,
            name=gate.device_name,
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        gate = self._gate
        try:
            await self.coordinator.client.async_open_gate(gate.device_id, gate.resource_id)
        except SummitError as err:
            raise HomeAssistantError(f"Failed to open {gate.name}: {err}") from err
