"""Text input sensors for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up text input entities."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[TextEntity] = []
    entities.append(EVSENicknameText(coordinator))

    async_add_entities(entities)


class EVSENicknameText(EVSEMasterEntity, TextEntity):
    _attr_translation_key = "nickname"
    _unique_id_key = "nickname"
    _attr_icon = "mdi:tag-text"
    _attr_mode = "text"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> str | None:
        """Get current nickname from device info."""
        return self.entry.device.nickname

    async def async_set_value(self, value: str) -> None:
        """Set the nickname."""
        await self.coordinator.async_set_nickname(value)
