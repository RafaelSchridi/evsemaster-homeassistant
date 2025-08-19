"""Basic sensors for EVSEMaster integration (minimal)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower,UnitOfEnergy,UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN  # noqa: F401
from .coordinator import EVSEMasterDataUpdateCoordinator,DataSchema
from .evsemaster.data_types import EvseStatus, ChargingStatus, CurrentStateEnum,PlugStateEnum


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    entities.append(EVSEStateSensor(coordinator))
    entities.append(EVSECurrentPowerSensor(coordinator))
    entities.append(EVSEPlugStateSensor(coordinator))
    entities.append(EVSEInnerTemperatureSensor(coordinator))
    entities.append(EVSEOuterTemperatureSensor(coordinator))
    entities.append(EVSETotalKwhSensor(coordinator))

    async_add_entities(entities)


class _Base(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data
    


class EVSEStateSensor(_Base, SensorEntity):
    _attr_translation_key = "current_state"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_current_state"

    @property
    def native_value(self) -> str | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_state.name


class EVSECurrentPowerSensor(_Base, SensorEntity):
    _attr_translation_key = "current_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_current_power"

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_power

class EVSEPlugStateSensor(_Base, SensorEntity):
    _attr_translation_key = "plug_state"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_plug_state"

    @property
    def native_value(self) -> str | None:
        status: EvseStatus = self.entry.status
        if status and status.plug_state is not None:
            return PlugStateEnum(status.plug_state).name
        return None
    
class EVSEInnerTemperatureSensor(_Base, SensorEntity):
    _attr_translation_key = "inner_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    # FIXME: you can change the unit on the EVSE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_inner_temperature"

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.inner_temperature
        
class EVSEOuterTemperatureSensor(_Base, SensorEntity):
    _attr_translation_key = "outer_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    # FIXME: you can change the unit on the EVSE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_outer_temperature"

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.outer_temperature
        

class EVSETotalKwhSensor(_Base, SensorEntity):
    _attr_translation_key = "total_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_total_kwh"
        
    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.total_kwh