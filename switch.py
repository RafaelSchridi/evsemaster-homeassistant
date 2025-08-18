"""Charging switch for EVSEMaster (minimal)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    entities.append(EVSEChargingSwitch(coordinator))
    async_add_entities(entities)

class _BaseSwitch(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE switches."""

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data
    

class EVSEChargingSwitch(_BaseSwitch, SwitchEntity):
    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.entry.device.serial_number}_charging_switch"
        self._attr_name = "Charging"
        self._attr_icon = "mdi:ev-station"
        self._attr_device_info = coordinator.data.device.get_attr_device_info()


    @property
    def is_on(self) -> bool:
        status: EvseStatus = self.entry.status
        if status and status.current_state:
            try:
                return status.current_state == CurrentStateEnum.CHARGING
            except Exception:
                return False
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_start_charging(self.entry.device.serial_number)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_charging(self.entry.device.serial_number)
