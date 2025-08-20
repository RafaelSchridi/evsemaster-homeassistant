"""Button platform for EVSEMaster integration (minimal)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EVSEMasterDataUpdateCoordinator, DataSchema
from evsemaster.data_types import EvseStatus, CurrentStateEnum

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up start/stop charging buttons in minimal style."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities: list[ButtonEntity] = []
    entities.append(EVSEStartChargingButton(coordinator))
    entities.append(EVSEStopChargingButton(coordinator))

    async_add_entities(entities)


class _BaseButton(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.data.device.get_attr_device_info()

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data


class EVSEStartChargingButton(_BaseButton, ButtonEntity):
    _attr_translation_key = "start_charging"
    _attr_icon = "mdi:play"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_unique_id = f"{serial}_start_charging_button"

    @property
    def available(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status and status.current_state is not None:
            return status.current_state != CurrentStateEnum.CHARGING
        return False

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_start_charging(self.entry.device.serial_number)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error starting charging on %s: %s", self.entry.device.serial_number, err)


class EVSEStopChargingButton(_BaseButton, ButtonEntity):
    _attr_translation_key = "stop_charging"
    _attr_icon = "mdi:stop"

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        serial = self.entry.device.serial_number
        self._attr_unique_id = f"{serial}_stop_charging_button"

    @property
    def available(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status and status.current_state is not None:
            return status.current_state == CurrentStateEnum.CHARGING
        return False

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_stop_charging(self.entry.device.serial_number)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error stopping charging on %s: %s", self.entry.device.serial_number, err)
