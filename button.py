"""Button platform for EVSEMaster integration (minimal)."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EVSEMasterDataUpdateCoordinator, DataSchema
from .evse_loader import data_types

# Import specific classes from the modules
EvseStatus = data_types.EvseStatus
CurrentStateEnum = data_types.CurrentStateEnum

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

    async def async_press(
        self,
        max_amps: int | None = None,
        duration_hours: float | None = None,
        start_datetime: str | None = None,
    ) -> None:
        await self.coordinator.async_start_charging(
            self.entry.device.serial_number,
            max_amps,
            start_datetime,
            duration_hours,
        )


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
        await self.coordinator.async_stop_charging()
