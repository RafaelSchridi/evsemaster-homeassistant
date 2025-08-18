"""Number platform for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
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
    """Set up the number platform."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    
    entities = []
    
    for evse_serial, evse_data in coordinator.data.items():
        entities.append(EVSEMaxCurrentNumber(coordinator, evse_serial))
    
    async_add_entities(entities)


class EVSEBaseNumber(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE number entities."""

    def __init__(
        self,
        coordinator: EVSEMasterDataUpdateCoordinator,
        evse_serial: str,
        number_type: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.evse_serial = evse_serial
        self.number_type = number_type
        
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


class EVSEMaxCurrentNumber(EVSEBaseNumber, NumberEntity):
    """Number entity for EVSE maximum current setting."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, evse_serial, "max_current")
        self._attr_unique_id = f"{evse_serial}_max_current"
        self._attr_name = "Maximum Current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_icon = "mdi:current-ac"
        
        # Set min/max based on EVSE capabilities
        info = self.evse_data.get("info", {})
        max_electricity = info.get("maxElectricity", 32)
        
        self._attr_native_min_value = 6.0  # Minimum charging current
        self._attr_native_max_value = float(max_electricity)
        self._attr_native_step = 1.0

    @property
    def native_value(self) -> float | None:
        """Return the current maximum current setting."""
        config = self.evse_data.get("config", {})
        return config.get("maxElectricity")

    @property
    def available(self) -> bool:
        """Return true if entity is available."""
        # Only available if EVSE is online and logged in
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the maximum current."""
        try:
            amps = int(value)
            success = await self.coordinator.async_set_max_electricity(
                self.evse_serial, amps
            )
            if success:
                await self.coordinator.async_request_refresh()
                _LOGGER.info(
                    "Set max current to %d A on %s", amps, self.evse_serial
                )
            else:
                _LOGGER.error(
                    "Failed to set max current on %s", self.evse_serial
                )
        except Exception as err:
            _LOGGER.error(
                "Error setting max current on %s: %s", self.evse_serial, err
            )
