"""Number input sensors for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EVSEMasterDataUpdateCoordinator, DataSchema
from .evse_loader import data_types

# Import specific classes from the modules
EvseStatus = data_types.EvseStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number input entities."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[NumberEntity] = []
    entities.append(EVSEMaxAmpsNumber(coordinator))

    async_add_entities(entities)


class _BaseNumber(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data


class EVSEMaxAmpsNumber(_BaseNumber, NumberEntity):
    _attr_translation_key = "max_amps"
    _attr_icon = "mdi:flash"
    _attr_native_min_value = 6
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "A"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_native_max_value = self.entry.device.max_amps
        self._attr_unique_id = f"{serial}_configured_max_amps"

    @property
    def native_value(self) -> float | None:
        """Get current max amps setting."""
        if self.entry.device:
            return float(self.entry.device.configured_max_amps)
        return None

    @property
    def available(self) -> bool:
        """Check if entity is available."""
        status: EvseStatus | None = self.entry.status
        if status and self.entry.device and self.entry.device.configured_max_amps is not None:
            return True
        return False

    async def async_set_native_value(self, value: float) -> None:
        """Set the max amps."""
        await self.coordinator.async_set_max_amps(int(value))