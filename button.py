"""Button platform for EVSEMaster integration (minimal)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EVSEMasterDataUpdateCoordinator
from .entity import EVSEMasterEntity
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


class EVSEStartChargingButton(EVSEMasterEntity, ButtonEntity):
    _attr_translation_key = "start_charging"
    _unique_id_key = "start_charging_button"
    _attr_icon = "mdi:play"

    @property
    def available(self) -> bool:
        status: EvseStatus | None = self.entry.status
        return bool(status and status.current_state is not None)

    async def async_press(
        self,
        max_amps: int | None = None,
        duration_hours: float | None = None,
        start_datetime: str | None = None,
    ) -> None:
        await self.coordinator.async_start_charging(
            max_amps,
            start_datetime,
            duration_hours,
        )


class EVSEStopChargingButton(EVSEMasterEntity, ButtonEntity):
    _attr_translation_key = "stop_charging"
    _unique_id_key = "stop_charging_button"
    _attr_icon = "mdi:stop"

    @property
    def available(self) -> bool:
        status: EvseStatus | None = self.entry.status
        if status and status.current_state is not None:
            return status.current_state != CurrentStateEnum.NOT_CONNECTED
        return False

    async def async_press(self) -> None:
        await self.coordinator.async_stop_charging()
