"""Number input sensors for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EVSEMasterDataUpdateCoordinator
from .entity import EVSEMasterEntity

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


class EVSEMaxAmpsNumber(EVSEMasterEntity, NumberEntity):
    _attr_translation_key = "max_amps"
    _unique_id_key = "configured_max_amps"
    _attr_native_min_value = 6
    _attr_icon = "mdi:flash"
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_max_value(self) -> float:
        """Device hardware limit; read live, it is not known when entities are created."""
        return float(self.entry.device.max_amps)

    @property
    def native_value(self) -> float | None:
        """Get current max amps setting."""
        if self.entry.device:
            return float(self.entry.device.configured_max_amps)
        return None

    @property
    def available(self) -> bool:
        """Unavailable mid-charge on a model that only applies the amperage at session start."""
        if not self.entry.status:
            return False
        device = self.coordinator.device
        if not device:
            return False
        if device.is_charging and not device.capabilities.amps_while_charging:
            return False
        return True

    async def async_set_native_value(self, value: float) -> None:
        """Set the max amps."""
        await self.coordinator.async_set_max_amps(int(value))
