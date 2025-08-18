"""Text platform for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
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
    """Set up the text platform."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    
    entities = []
    
    for evse_serial, evse_data in coordinator.data.items():
        entities.append(EVSENameText(coordinator, evse_serial))
    
    async_add_entities(entities)


class EVSEBaseText(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE text entities."""

    def __init__(
        self,
        coordinator: EVSEMasterDataUpdateCoordinator,
        evse_serial: str,
        text_type: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self.evse_serial = evse_serial
        self.text_type = text_type
        
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


class EVSENameText(EVSEBaseText, TextEntity):
    """Text entity for EVSE name."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, evse_serial, "name")
        self._attr_unique_id = f"{evse_serial}_name"
        self._attr_name = "Name"
        self._attr_icon = "mdi:rename-box"
        self._attr_mode = "text"
        self._attr_max_length = 16  # EVSE name limit

    @property
    def native_value(self) -> str | None:
        """Return the current EVSE name."""
        config = self.evse_data.get("config", {})
        return config.get("name")

    @property
    def available(self) -> bool:
        """Return true if entity is available."""
        # Only available if EVSE is online and logged in
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
        )

    async def async_set_value(self, value: str) -> None:
        """Set the EVSE name."""
        try:
            success = await self.coordinator.async_set_name(
                self.evse_serial, value
            )
            if success:
                await self.coordinator.async_request_refresh()
                _LOGGER.info(
                    "Set name to '%s' on %s", value, self.evse_serial
                )
            else:
                _LOGGER.error(
                    "Failed to set name on %s", self.evse_serial
                )
        except Exception as err:
            _LOGGER.error(
                "Error setting name on %s: %s", self.evse_serial, err
            )
