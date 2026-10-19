"""Select entities for EVSEMaster integration."""

from __future__ import annotations

from evsemaster import LanguageEnum
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EVSEMasterDataUpdateCoordinator
from .entity import EVSEMasterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    async_add_entities([EVSELanguageSelect(coordinator)])


class EVSELanguageSelect(EVSEMasterEntity, SelectEntity):
    _attr_translation_key = "language"
    _unique_id_key = "language"
    _attr_icon = "mdi:translate"
    _attr_entity_category = EntityCategory.CONFIG
    # UNKNOWN is a reading, not something the charger can be set to
    _attr_options = [language.name.lower() for language in LanguageEnum if language is not LanguageEnum.UNKNOWN]

    @property
    def current_option(self) -> str | None:
        language = self.entry.device.language
        if language is None or language is LanguageEnum.UNKNOWN:
            return None
        return language.name.lower()

    async def async_select_option(self, option: str) -> None:
        """Set the charger's display language."""
        await self.coordinator.async_set_language(LanguageEnum[option.upper()])
