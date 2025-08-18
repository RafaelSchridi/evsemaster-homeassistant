"""Select platform for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EVSEMasterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    
    entities = []
    
    for evse_serial, evse_data in coordinator.data.items():
        entities.extend([
            EVSELanguageSelect(coordinator, evse_serial),
            EVSETemperatureUnitSelect(coordinator, evse_serial),
        ])
    
    async_add_entities(entities)


class EVSEBaseSelect(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE select entities."""

    def __init__(
        self,
        coordinator: EVSEMasterDataUpdateCoordinator,
        evse_serial: str,
        select_type: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.evse_serial = evse_serial
        self.select_type = select_type
        
        evse_data = coordinator.data.get(evse_serial, {})
        info = evse_data.get("info", {})
        brand = info.get("brand", "Unknown")
        model = info.get("model", "EVSE")
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, evse_serial)},
            "name": f"{brand} {model}",
            "manufacturer": brand,
            "model": model,
            "serial_number": evse_serial,
        }

    @property
    def evse_data(self) -> dict:
        """Get EVSE data from coordinator."""
        return self.coordinator.data.get(self.evse_serial, {})


class EVSELanguageSelect(EVSEBaseSelect, SelectEntity):
    """Select entity for EVSE language setting."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, evse_serial, "language")
        self._attr_unique_id = f"{evse_serial}_language"
        self._attr_name = "Language"
        self._attr_icon = "mdi:translate"
        self._attr_options = [
            "ENGLISH",
            "CHINESE_SIMPLIFIED",
            "CHINESE_TRADITIONAL",
            "GERMAN",
            "SPANISH",
            "FRENCH",
            "ITALIAN",
            "JAPANESE",
            "KOREAN",
            "PORTUGUESE",
            "RUSSIAN",
        ]

    @property
    def current_option(self) -> str | None:
        """Return the current language setting."""
        config = self.evse_data.get("config", {})
        return config.get("language")

    @property
    def available(self) -> bool:
        """Return true if entity is available."""
        # Only available if EVSE is online and logged in
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
        )

    async def async_select_option(self, option: str) -> None:
        """Set the language."""
        try:
            # This would need to be implemented in the coordinator
            # For now, just log the action
            _LOGGER.info(
                "Setting language to %s on %s", option, self.evse_serial
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(
                "Error setting language on %s: %s", self.evse_serial, err
            )


class EVSETemperatureUnitSelect(EVSEBaseSelect, SelectEntity):
    """Select entity for EVSE temperature unit setting."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, evse_serial, "temperature_unit")
        self._attr_unique_id = f"{evse_serial}_temperature_unit"
        self._attr_name = "Temperature Unit"
        self._attr_icon = "mdi:thermometer"
        self._attr_options = ["CELSIUS", "FAHRENHEIT"]

    @property
    def current_option(self) -> str | None:
        """Return the current temperature unit setting."""
        config = self.evse_data.get("config", {})
        return config.get("temperatureUnit")

    @property
    def available(self) -> bool:
        """Return true if entity is available."""
        # Only available if EVSE is online and logged in
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
        )

    async def async_select_option(self, option: str) -> None:
        """Set the temperature unit."""
        try:
            # This would need to be implemented in the coordinator
            # For now, just log the action
            _LOGGER.info(
                "Setting temperature unit to %s on %s",
                option,
                self.evse_serial
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(
                "Error setting temperature unit on %s: %s",
                self.evse_serial,
                err
            )
