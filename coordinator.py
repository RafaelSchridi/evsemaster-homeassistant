"""Data update coordinator for EVSEMaster integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from evsemaster.evse_protocol import SimpleEVSEProtocol
from evsemaster.data_types import EvseStatus, ChargingStatus,BaseSchema,EvseDeviceInfo

_LOGGER = logging.getLogger(__name__)

class DeviceSchema(EvseDeviceInfo):

    def get_attr_device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant."""
        return {
            "identifiers": {(DOMAIN, self.serial_number)},
            "name": f"{self.model}", # manufacturer + model or just model?
            "manufacturer": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "hw_version": self.hardware_version,
            }

class DataSchema(BaseSchema):
    """Schema for EVSE data."""

    status: EvseStatus | None = None
    charging_status: ChargingStatus | None = None
    device: DeviceSchema = DeviceSchema()

class EVSEMasterDataUpdateCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.password = entry.data[CONF_PASSWORD]
        self._connected = False
        self.data: DataSchema = DataSchema()

        # Protocol with local-push callback
        self.proto = SimpleEVSEProtocol(
            host=self.host,
            password=self.password,
            event_callback=self._on_protocol_event,
        )

    def _ensure_serial(self) -> tuple[str, DataSchema]:
        """Ensure the serial number is set in the data schema."""
        proto_device = self.proto.get_latest_device_info()
        if  self.data.device != proto_device and proto_device is not None:
            self.data.device = DeviceSchema.model_validate(proto_device.model_dump())

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
            if changed:
                self.async_set_updated_data(self.data)
        self.hass.async_create_task(_handle())

    async def _async_update_data(self) -> dict[str, Any]:
        """Ensure connection and login; return latest cached snapshot."""
        try:
            if not self._connected:
                ok = await self.proto.connect()
                if not ok:
                    raise UpdateFailed("Failed to create sockets to connect to EVSE")
                self._connected = True
                _LOGGER.info("Connected to EVSE on %s", self.host)

            if not self.proto.is_logged_in:
                success = await self.proto.login()
                if not success:
                    raise UpdateFailed("Failed to login to EVSE")
                _LOGGER.info("Logged in to EVSE")

            # Trigger a status push; listener loop will call back, but return current cache immediately
            await self.proto.request_status()

            self._ensure_serial()
            return self.data
        except Exception as err:
            _LOGGER.error("Error updating EVSE data: %s", err)
            raise UpdateFailed(f"Error communicating with EVSE: {err}") from err

    async def async_shutdown(self) -> None:
        await self.proto.disconnect()
        self._connected = False
        _LOGGER.info("EVSE client disconnected")

    async def async_start_charging(self, evse_serial: str, max_amps: int = 16) -> bool:
        try:
            return await self.proto.start_charging(max_amps)
        except Exception as err:
            _LOGGER.error("Error starting charging on %s: %s", evse_serial, err)
            return False

    async def async_stop_charging(self, evse_serial: str) -> bool:
        try:
            return await self.proto.stop_charging()
        except Exception as err:
            _LOGGER.error("Error stopping charging on %s: %s", evse_serial, err)
            return False
