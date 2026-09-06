"""Binary sensors for EVSEMaster (minimal)."""

from __future__ import annotations

from evsemaster import CurrentStateEnum, EvseStatus, PlugStateEnum
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EVSEMasterDataUpdateCoordinator
from .entity import EVSEMasterEntity


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


class EVSEPluggedInBinarySensor(EVSEMasterEntity, BinarySensorEntity):
    _attr_translation_key = "plug_state"
    _unique_id_key = "plug_state_binary"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def is_on(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status:
            return status.plug_state != PlugStateEnum.DISCONNECTED
        return False


class EVSEChargingBinarySensor(EVSEMasterEntity, BinarySensorEntity):
    _attr_translation_key = "charging_state"
    _unique_id_key = "charging_binary"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status:
            return status.current_state == CurrentStateEnum.CHARGING
        return False
