"""Binary sensors for EVSEMaster (minimal)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EVSEMasterDataUpdateCoordinator, DataSchema
from .evse_loader import data_types

# Import specific classes from the modules
EvseStatus = data_types.EvseStatus
PlugStateEnum = data_types.PlugStateEnum
CurrentStateEnum = data_types.CurrentStateEnum


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up minimal binary sensors: plugged-in and charging."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[BinarySensorEntity] = []
    entities.append(EVSEPluggedInBinarySensor(coordinator))
    entities.append(EVSEChargingBinarySensor(coordinator))

    async_add_entities(entities)


class _Base(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data


class EVSEPluggedInBinarySensor(_Base, BinarySensorEntity):
    _attr_translation_key = "plug_state"
    _attr_device_class = BinarySensorDeviceClass.PLUG


    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_unique_id = f"{serial}_plug_state_binary"

    @property
    def is_on(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status:
            return status.plug_state != PlugStateEnum.DISCONNECTED
        return False


class EVSEChargingBinarySensor(_Base, BinarySensorEntity):
    _attr_translation_key = "charging_state"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_unique_id = f"{serial}_charging_binary"

    @property
    def is_on(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status:
            return status.current_state == CurrentStateEnum.CHARGING
        return False
