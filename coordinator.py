"""Data update coordinator for EVSEMaster integration."""

from __future__ import annotations

from datetime import timedelta,datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .evse_loader import evse_protocol, data_types

# Import specific classes from the modules
SimpleEVSEProtocol = evse_protocol.SimpleEVSEProtocol
EvseStatus = data_types.EvseStatus
ChargingStatus = data_types.ChargingStatus
BaseSchema = data_types.BaseSchema
EvseDeviceInfo = data_types.EvseDeviceInfo

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
            "name_by_user": self.nickname if self.nickname else None,
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
            config_entry=entry,
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.password = entry.data[CONF_PASSWORD]
        self._connected = False
        self.data: DataSchema = DataSchema()
        self.secondary_timer = datetime.utcnow()

        self.proto = SimpleEVSEProtocol(
            host=self.host,
            password=self.password,
            event_callback=self._on_protocol_event,
        )

    def _ensure_serial(self) -> tuple[str, DataSchema]:
        """Ensure the serial number is set in the data schema."""
        proto_device = self.proto.get_latest_device_info()
        if proto_device and proto_device.serial_number != self.data.device.serial_number:
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
            elif event_type == EvseDeviceInfo.__name__ and isinstance(payload, EvseDeviceInfo):
                self.data.device = DeviceSchema.model_validate(payload.model_dump())
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

            # data is pushed via callback; just request an update
            await self.proto.request_status()
            # every x minutes request full device info to catch changes
            if (self.secondary_timer + timedelta(minutes=30) < datetime.utcnow()):
                success = await self.proto.request_essentials()
                if not success:
                     _LOGGER.warning("Failed to refresh device info from EVSE")
                else:
                    _LOGGER.info("Refreshed device info from EVSE")

            self._ensure_serial()
            return self.data
        except Exception as err:
            _LOGGER.error("Error updating EVSE data: %s", err)
            raise UpdateFailed(f"Error communicating with EVSE: {err}") from err

    async def async_shutdown(self) -> None:
        await self.proto.disconnect()
        self._connected = False
        _LOGGER.info("EVSE client disconnected")


    async def async_start_charging(
        self, 
        max_amps: int | None = None,
        start_datetime: datetime| str | None = None,
        duration_hours: float | None = None,
    ) -> bool:
        """Start charging with advanced parameters."""
        try:
            minutes = None
            if duration_hours is not None:
                minutes = int(duration_hours * 60)
            if isinstance(start_datetime, str):
                start_datetime = datetime.fromisoformat(start_datetime)
            _LOGGER.info(
                f"Starting charging on {self.data.device.serial_number}: amps={max_amps}, duration={minutes}m, start={start_datetime}"
            )
            return await self.proto.start_charging(max_amps,start_datetime,minutes)
        except Exception as err:
            _LOGGER.error("Error starting charging on %s: %s", self.data.device.serial_number, err)
            return False
        
    async def async_stop_charging(self) -> bool:
        try:
            return await self.proto.stop_charging()
        except Exception as err:
            _LOGGER.error("Error stopping charging on %s: %s", self.data.device.serial_number, err)
            return False


    async def async_set_nickname(self, nickname: str) -> bool:
        """Set device nickname."""
        try:
            return await self.proto.set_nickname(nickname)
        except Exception as err:
            _LOGGER.error("Error setting nickname on %s: %s", self.data.device.serial_number, err)
            return False

    async def async_set_max_amps(self, amperage: int) -> bool:
        """Set maximum output amperage."""
        try:
            return await self.proto.set_output_amperage(amperage)
        except Exception as err:
            _LOGGER.error("Error setting max amperage on %s: %s", self.data.device.serial_number, err)
            return False
