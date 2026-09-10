"""Data update coordinator for EVSEMaster integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from evsemaster import (
    ChargingStatus,
    CurrentStateEnum,
    EvseDevice,
    EvseDeviceInfo,
    EvseStatus,
    now_aware,
)
from evsemaster.data_types import BaseSchema
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .hub import async_get_listener

_LOGGER = logging.getLogger(__name__)

ESSENTIALS_INTERVAL = timedelta(minutes=30)


class DataSchema(BaseSchema):
    """Schema for EVSE data."""

    status: EvseStatus | None = None
    charging_status: ChargingStatus | None = None
    device: EvseDeviceInfo = EvseDeviceInfo()


class EVSEMasterDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.unique_id or entry.data[CONF_HOST]}",
            config_entry=entry,
            update_interval=timedelta(seconds=60),
            update_method=self._async_update_data,
            always_update=True,
        )
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.password = entry.data[CONF_PASSWORD]
        self.data: DataSchema = DataSchema()
        self.device: EvseDevice | None = None
        self._essentials_refreshed = dt_util.utcnow()

    async def async_init(self) -> None:
        """Register this charger with the shared listener (cannot await in __init__)."""
        listener = await async_get_listener(self.hass)
        self.device = await listener.async_add_device(self.host, self.password, on_event=self._on_protocol_event)

    @property
    def unique_id(self) -> str:
        """This charger's unique_id, as stored on the config entry."""
        return self.entry.unique_id

    @property
    def device_name(self) -> str | None:
        """Model and nickname together, so several chargers of one model stay distinguishable."""
        device = self.data.device
        return " ".join(filter(None, (device.model, device.nickname))) or None

    @property
    def device_info(self) -> dict[str, Any]:
        """Device registry entry for this charger."""
        device = self.data.device
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.device_name,
            "manufacturer": device.brand,
            "model": device.model,
            "serial_number": self.unique_id,
            "hw_version": device.hardware_version,
        }

    def _ensure_serial(self) -> None:
        """Copy freshly parsed device info into the coordinator data."""
        proto_device = self.device.get_latest_device_info() if self.device else None
        if proto_device and proto_device.serial_number != self.data.device.serial_number:
            self.data.device = proto_device

    def _on_protocol_event(self, event_type: str, payload: Any) -> None:
        """Receive local-push events from protocol and push to HA."""

        async def _handle() -> None:
            self._ensure_serial()
            changed = False
            if event_type == EvseStatus.__name__ and isinstance(payload, EvseStatus):
                self.data.status = payload
                changed = True
            elif event_type == ChargingStatus.__name__ and isinstance(payload, ChargingStatus):
                self.data.charging_status = payload
                changed = True
            elif event_type == EvseDeviceInfo.__name__ and isinstance(payload, EvseDeviceInfo):
                self.data.device = payload
                self._async_follow_device_name()
                changed = True
            if changed:
                self.async_set_updated_data(self.data)

        self.hass.async_create_task(_handle())

    async def _async_update_data(self) -> DataSchema:
        """Ensure the session is alive; data itself arrives via the push callback."""
        try:
            if not self.device.is_logged_in:
                if not await self.device.login():
                    raise UpdateFailed("Failed to login to EVSE")
                _LOGGER.info("Logged in to EVSE %s", self.host)
                self._async_adopt_serial()

            # data is pushed via callback; just request an update
            await self.device.request_status()
            # every x minutes request full device info to catch changes
            if self._essentials_refreshed + ESSENTIALS_INTERVAL < dt_util.utcnow():
                self._essentials_refreshed = dt_util.utcnow()
                await self.device.request_essentials()
                _LOGGER.debug("Refreshed device info from EVSE")

            self._ensure_serial()
            return self.data
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error updating EVSE data: %s", err)
            raise UpdateFailed(f"Error communicating with EVSE: {err}") from err

    def _async_follow_device_name(self) -> None:
        """Re-apply the device name, whose parts arrive after the device is registered."""
        name = self.device_name
        if not name:
            return
        registry = dr.async_get(self.hass)
        # scoped to this entry rather than looked up by identifier: identifiers are no longer
        # unique across config entries, and async_get_device(identifiers=...) is on its way out
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            if device.name != name:
                registry.async_update_device(device.id, name=name)

    def _async_adopt_serial(self) -> None:
        """Entries created before multi-device support have no unique id; backfill the serial."""
        if self.entry.unique_id or not self.device.serial:
            return
        _LOGGER.info("Adopting serial %s as unique id for %s", self.device.serial, self.host)
        self.hass.config_entries.async_update_entry(self.entry, unique_id=self.device.serial)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self.device:
            listener = self.hass.data.get(DOMAIN)
            if listener:
                await listener.async_remove_device(self.device)
            self.device = None
            _LOGGER.info("EVSE client disconnected")

    async def async_start_charging(
        self,
        max_amps: int | None = None,
        start_datetime: datetime | str | None = None,
        duration_hours: float | None = None,
    ) -> bool:
        """Start charging with advanced parameters."""
        try:
            minutes = None
            if duration_hours is not None:
                minutes = int(duration_hours * 60)
            if isinstance(start_datetime, str):
                start_datetime = datetime.fromisoformat(start_datetime)
            if start_datetime and start_datetime.tzinfo is None:
                start_datetime = start_datetime.replace(tzinfo=now_aware().tzinfo)
            if start_datetime and start_datetime > now_aware() + timedelta(hours=24):
                raise ValueError("Reservation cannot be scheduled more than 24 hours in the future")
            if max_amps is not None:
                if max_amps > self.data.device.max_amps:
                    raise ValueError(
                        f"Requested max_amps {max_amps} exceeds device hardware limit of {self.data.device.max_amps} A"
                    )
                if max_amps > self.data.device.configured_max_amps:
                    _LOGGER.warning(
                        "Requested max_amps %d exceeds configured max %d, clamping",
                        max_amps,
                        self.data.device.configured_max_amps,
                    )
                    max_amps = self.data.device.configured_max_amps
            _LOGGER.info(
                f"Starting charging on {self.unique_id}: amps={max_amps}, duration={minutes}m, start={start_datetime}"
            )
            return await self.device.start_charging(max_amps, start_datetime, minutes)
        except Exception as err:
            _LOGGER.error("Error starting charging on %s: %s", self.unique_id, err)
            raise HomeAssistantError(str(err)) from err

    async def async_stop_charging(self) -> bool:
        status = self.data.status
        if status and status.current_state == CurrentStateEnum.NOT_CONNECTED:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="nothing_to_stop")
        try:
            return await self.device.stop_charging()
        except Exception as err:
            _LOGGER.error("Error stopping charging on %s: %s", self.unique_id, err)
            raise HomeAssistantError(str(err)) from err

    async def async_set_nickname(self, nickname: str) -> bool:
        """Set device nickname."""
        try:
            return await self.device.set_nickname(nickname)
        except Exception as err:
            _LOGGER.error("Error setting nickname on %s: %s", self.unique_id, err)
            raise HomeAssistantError(str(err)) from err

    async def async_set_max_amps(self, amperage: int) -> bool:
        """Set maximum output amperage."""
        try:
            return await self.device.set_output_amperage(amperage)
        except Exception as err:
            _LOGGER.error("Error setting max amperage on %s: %s", self.unique_id, err)
            raise HomeAssistantError(str(err)) from err
