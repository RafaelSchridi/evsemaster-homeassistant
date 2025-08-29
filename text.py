"""Text input sensors for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
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
    """Set up text input entities."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[TextEntity] = []
    entities.append(EVSENicknameText(coordinator))

    async_add_entities(entities)


class _BaseText(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data


class EVSENicknameText(_BaseText, TextEntity):
    _attr_translation_key = "nickname"
    _attr_icon = "mdi:tag-text"
    _attr_mode = "text"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_unique_id = f"{serial}_nickname"

    @property
    def native_value(self) -> str | None:
        """Get current nickname from device info."""
        return self.entry.device.nickname

    async def async_set_value(self, value: str) -> None:
        """Set the nickname."""
        await self.coordinator.async_set_nickname(value)
