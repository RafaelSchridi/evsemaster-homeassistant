"""Basic sensors for EVSEMaster integration (minimal)."""

from __future__ import annotations

from datetime import datetime

from evsemaster import EvseStatus, PlugStateEnum
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
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
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    entities.append(EVSEStateSensor(coordinator))
    entities.append(EVSECurrentPowerSensor(coordinator))
    entities.append(EVSEPlugStateSensor(coordinator))
    entities.append(EVSEInnerTemperatureSensor(coordinator))
    entities.append(EVSEOuterTemperatureSensor(coordinator))
    entities.append(EVSETotalKwhSensor(coordinator))
    entities.append(EVSEChargeKwhSensor(coordinator))
    entities.append(EVSEChargeDurationSensor(coordinator))
    entities.append(EVSESessionStartDatetimeSensor(coordinator))
    entities.append(EVSESessionMaxCurrentSensor(coordinator))
    entities.append(EVSEReservationDatetimeSensor(coordinator))
    entities.append(EVSEReservationDurationSensor(coordinator))
    entities.append(EVSETimeDeltaSensor(coordinator))
    entities.append(EVSELastAliveSensor(coordinator))
    entities.append(EVSEL1VoltageSensor(coordinator))
    entities.append(EVSEL2VoltageSensor(coordinator))
    entities.append(EVSEL3VoltageSensor(coordinator))
    entities.append(EVSEL1CurrentSensor(coordinator))
    entities.append(EVSEL2CurrentSensor(coordinator))
    entities.append(EVSEL3CurrentSensor(coordinator))

    async_add_entities(entities)


class EVSEStateSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "current_state"
    _unique_id_key = "current_state"

    @property
    def native_value(self) -> str | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_state.name.lower()


class EVSECurrentPowerSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "current_power"
    _unique_id_key = "current_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.current_power


class EVSEPlugStateSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "plug_state"
    _unique_id_key = "plug_state"

    @property
    def native_value(self) -> str | None:
        status: EvseStatus = self.entry.status
        if status and status.plug_state is not None:
            return PlugStateEnum(status.plug_state).name.lower()
        return None


class EVSEInnerTemperatureSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "inner_temperature"
    _unique_id_key = "inner_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    # FIXME: you can change the unit on the EVSE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.inner_temperature


class EVSEOuterTemperatureSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "outer_temperature"
    _unique_id_key = "outer_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    # FIXME: you can change the unit on the EVSE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.outer_temperature


class EVSETotalKwhSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "total_kwh"
    _unique_id_key = "total_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        status: EvseStatus = self.entry.status
        if status:
            return status.total_kwh


class EVSEChargeKwhSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "charge_kwh"
    _unique_id_key = "charge_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        cstatus = self.entry.charging_status
        if cstatus:
            return cstatus.charge_kwh


class EVSEChargeDurationSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "charge_duration"
    _unique_id_key = "charge_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> int | None:
        cstatus = self.entry.charging_status
        if cstatus:
            return cstatus.duration_seconds


class EVSESessionStartDatetimeSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "session_start_datetime"
    _unique_id_key = "session_start_datetime"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        cstatus = self.entry.charging_status
        if cstatus and isinstance(cstatus.set_datetime, datetime):
            return cstatus.set_datetime
        return None


class EVSESessionMaxCurrentSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "session_max_current"
    _unique_id_key = "session_max_current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = SensorDeviceClass.CURRENT

    @property
    def native_value(self) -> int | None:
        cstatus = self.entry.charging_status
        if cstatus:
            return cstatus.max_electricity
        return None


class EVSEReservationDatetimeSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "reservation_datetime"
    _unique_id_key = "reservation_datetime"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        cstatus = self.entry.charging_status
        if cstatus and isinstance(cstatus.reservation_datetime, datetime):
            return cstatus.reservation_datetime
        return None


class EVSEReservationDurationSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "reservation_duration"
    _unique_id_key = "reservation_max_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def native_value(self) -> int | None:
        cstatus = self.entry.charging_status
        if cstatus and cstatus.max_duration_minutes is not None:
            return cstatus.max_duration_minutes
        return None


class EVSETimeDeltaSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "time_delta"
    _unique_id_key = "time_delta"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int | None:
        device = self.coordinator.device
        return device.time_delta if device else None


class EVSELastAliveSensor(EVSEMasterEntity, SensorEntity):
    _attr_translation_key = "last_alive"
    _unique_id_key = "last_alive"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # changes with almost every packet; kept out of the recorder unless someone is debugging
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> datetime | None:
        device = self.coordinator.device
        return device.last_alive if device else None


class _BasePhase(EVSEMasterEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        return self.entry.status is not None


class EVSEL1VoltageSensor(_BasePhase):
    _attr_translation_key = "l1_voltage"
    _unique_id_key = "l1_voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l1_voltage if status else None


class EVSEL2VoltageSensor(_BasePhase):
    _attr_translation_key = "l2_voltage"
    _unique_id_key = "l2_voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l2_voltage if status else None


class EVSEL3VoltageSensor(_BasePhase):
    _attr_translation_key = "l3_voltage"
    _unique_id_key = "l3_voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l3_voltage if status else None


class EVSEL1CurrentSensor(_BasePhase):
    _attr_translation_key = "l1_current"
    _unique_id_key = "l1_current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l1_amps if status else None


class EVSEL2CurrentSensor(_BasePhase):
    _attr_translation_key = "l2_current"
    _unique_id_key = "l2_current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l2_amps if status else None


class EVSEL3CurrentSensor(_BasePhase):
    _attr_translation_key = "l3_current"
    _unique_id_key = "l3_current"
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self) -> float | None:
        status = self.entry.status
        return status.l3_amps if status else None
