"""Basic sensors for EVSEMaster integration (minimal)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EVSEMasterDataUpdateCoordinator,DataSchema
from .evsemaster.data_types import EvseStatus, ChargingStatus, CurrentStateEnum


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up minimal sensors: state and charge energy."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    entities.append(EVSEStateSensor(coordinator))
    entities.append(EVSEChargeEnergySensor(coordinator))

    async_add_entities(entities)


class _Base(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data
    


class EVSEStateSensor(_Base, SensorEntity):
    """Shows the current EVSE state."""

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_current_state"
        self._attr_name = "EVSE State"

    @property
    def native_value(self) -> str | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_state.name


class EVSEChargeEnergySensor(_Base, SensorEntity):
    """Shows current charge session energy (kWh) if charging."""

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_charge_energy"
        self._attr_name = "Charge Energy"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_power
