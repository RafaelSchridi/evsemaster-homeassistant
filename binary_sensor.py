"""Binary sensor platform for EVSEMaster integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EVSEMasterDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    
    entities = []
    
    for evse_serial, evse_data in coordinator.data.items():
        entities.extend([
            EVSEOnlineBinarySensor(coordinator, evse_serial),
            EVSEConnectedBinarySensor(coordinator, evse_serial),
            EVSEChargingBinarySensor(coordinator, evse_serial),
            EVSEErrorBinarySensor(coordinator, evse_serial),
            EVSELoggedInBinarySensor(coordinator, evse_serial),
        ])
    
    async_add_entities(entities)


class EVSEBaseBinarySensor(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE binary sensors."""

    def __init__(
        self,
        coordinator: EVSEMasterDataUpdateCoordinator,
        evse_serial: str,
        sensor_type: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.evse_serial = evse_serial
        self.sensor_type = sensor_type
        
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


class EVSEOnlineBinarySensor(EVSEBaseBinarySensor, BinarySensorEntity):
    """Binary sensor for EVSE online status."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, evse_serial, "online")
        self._attr_unique_id = f"{evse_serial}_online"
        self._attr_name = "Online"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool | None:
        """Return true if EVSE is online."""
        return self.evse_data.get("isOnline", False)


class EVSEConnectedBinarySensor(EVSEBaseBinarySensor, BinarySensorEntity):
    """Binary sensor for EVSE connection status."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, evse_serial, "connected")
        self._attr_unique_id = f"{evse_serial}_connected"
        self._attr_name = "Connected"
        self._attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def is_on(self) -> bool | None:
        """Return true if a vehicle is connected."""
        state = self.evse_data.get("state", {})
        gun_state = state.get("gunState")
        return gun_state not in [None, "DISCONNECTED"]


class EVSEChargingBinarySensor(EVSEBaseBinarySensor, BinarySensorEntity):
    """Binary sensor for EVSE charging status."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, evse_serial, "charging")
        self._attr_unique_id = f"{evse_serial}_charging"
        self._attr_name = "Charging"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool | None:
        """Return true if EVSE is currently charging."""
        meta_state = self.evse_data.get("metaState")
        return meta_state == "CHARGING"


class EVSEErrorBinarySensor(EVSEBaseBinarySensor, BinarySensorEntity):
    """Binary sensor for EVSE error status."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, evse_serial, "error")
        self._attr_unique_id = f"{evse_serial}_error"
        self._attr_name = "Error"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        """Return true if EVSE has errors."""
        state = self.evse_data.get("state", {})
        errors = state.get("errors", [])
        return len(errors) > 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return error details as attributes."""
        state = self.evse_data.get("state", {})
        errors = state.get("errors", [])
        return {
            "error_count": len(errors),
            "errors": errors,
        }


class EVSELoggedInBinarySensor(EVSEBaseBinarySensor, BinarySensorEntity):
    """Binary sensor for EVSE login status."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, evse_serial, "logged_in")
        self._attr_unique_id = f"{evse_serial}_logged_in"
        self._attr_name = "Logged In"

    @property
    def is_on(self) -> bool | None:
        """Return true if logged in to EVSE."""
        return self.evse_data.get("isLoggedIn", False)
