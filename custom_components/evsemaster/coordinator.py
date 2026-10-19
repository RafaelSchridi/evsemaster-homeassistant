"""Data update coordinator for EVSEMaster integration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from typing import Any

from evsemaster import (
    ChargeRecord,
    ChargingStatus,
    EvseDevice,
    EvseDeviceInfo,
    EvseStatus,
    LanguageEnum,
    NotLoggedInError,
    UnsupportedOperationError,
    WeeklyPlan,
    WeeklyPlanSlot,
    now_aware,
)
from evsemaster.data_types import BaseSchema
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pydantic import ValidationError

from .const import DOMAIN
from .hub import async_get_listener

_LOGGER = logging.getLogger(__name__)

ESSENTIALS_INTERVAL = timedelta(minutes=30)


def record_store(hass: HomeAssistant, entry: ConfigEntry) -> Store:
    """Where the last finished session is kept across restarts."""
    return Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.last_record")


class DataSchema(BaseSchema):
    """Schema for EVSE data."""

    status: EvseStatus | None = None
    charging_status: ChargingStatus | None = None
    device: EvseDeviceInfo = EvseDeviceInfo()
    weekly_plan: WeeklyPlan | None = None
    last_record: ChargeRecord | None = None


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
        self._unsub_essentials: CALLBACK_TYPE | None = None
        self._store = record_store(hass, entry)

    async def async_init(self) -> None:
        """Register this charger with the shared listener (cannot await in __init__)."""
        saved = await self._store.async_load()
        if saved:
            try:
                self.data.last_record = ChargeRecord.model_validate(saved)
            except ValidationError:
                _LOGGER.debug("Dropping a stored session this library version cannot read")
        listener = await async_get_listener(self.hass)
        self.device = await listener.async_add_device(self.host, self.password, on_event=self._on_protocol_event)
        self._unsub_essentials = async_track_time_interval(
            self.hass, self._async_refresh_essentials, ESSENTIALS_INTERVAL
        )

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
    def display_name(self) -> str:
        """This charger as the user sees it in HA, a rename included."""
        devices = dr.async_entries_for_config_entry(dr.async_get(self.hass), self.entry.entry_id)
        if not devices:
            return self.device_name or self.host
        return devices[0].name_by_user or devices[0].name or self.host

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
            "sw_version": device.firmware_version,
            "hw_version": None,  # the registry keeps an old value until it is overwritten
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
                # a charger that dropped us announces every 3s; restarting the watchdog on that starves it
                self.async_update_listeners()
            elif event_type == WeeklyPlan.__name__ and isinstance(payload, WeeklyPlan):
                self.data.weekly_plan = payload
                self.async_update_listeners()
            elif event_type == ChargeRecord.__name__ and isinstance(payload, ChargeRecord):
                self.data.last_record = payload
                self.async_update_listeners()
                await self._store.async_save(payload.model_dump(mode="json"))
            if changed:
                self.async_set_updated_data(self.data)

        self.hass.async_create_task(_handle())

    async def _async_update_data(self) -> DataSchema:
        """Watchdog: every push restarts the countdown, so this only runs after 60s without one."""
        try:
            if not self.device.is_logged_in:
                if not await self.device.login():
                    raise UpdateFailed("Failed to login to EVSE")
                _LOGGER.info("Logged in to EVSE %s", self.host)
                self._async_adopt_serial()

            # data is pushed via callback; just request an update
            await self.device.request_status()
            self._ensure_serial()
            return self.data
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error updating EVSE data: %s", err)
            raise UpdateFailed(f"Error communicating with EVSE: {err}") from err

    async def _async_refresh_essentials(self, _now: datetime) -> None:
        """Re-read nickname and configured amps; the poll rarely runs while pushes flow."""
        if not self.device or not self.device.is_logged_in:
            return
        await self.device.request_essentials()

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
        if self._unsub_essentials:
            self._unsub_essentials()
            self._unsub_essentials = None
        if self.device:
            listener = self.hass.data.get(DOMAIN)
            if listener:
                await listener.async_remove_device(self.device)
            self.device = None
            _LOGGER.info("EVSE client disconnected")

    @contextmanager
    def _action_errors(self, unreachable_key: str = "not_responding") -> Iterator[dict[str, str]]:
        """Turn library refusals into translated errors that name this charger."""
        placeholders = {"device": self.display_name}
        try:
            yield placeholders
        except (NotLoggedInError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=unreachable_key, translation_placeholders=placeholders
            ) from err
        except UnsupportedOperationError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_operation",
                translation_placeholders={**placeholders, "error": str(err)},
            ) from err
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={**placeholders, "error": str(err)},
            ) from err

    async def async_start_charging(
        self,
        max_amps: int | None = None,
        start_datetime: datetime | str | None = None,
        duration_hours: float | None = None,
    ) -> bool:
        """Start charging with advanced parameters."""
        with self._action_errors() as placeholders:
            minutes = None
            if duration_hours is not None:
                minutes = int(duration_hours * 60)
            if isinstance(start_datetime, str):
                start_datetime = datetime.fromisoformat(start_datetime)
            if start_datetime and start_datetime.tzinfo is None:
                start_datetime = start_datetime.replace(tzinfo=now_aware().tzinfo)
            if start_datetime and start_datetime > now_aware() + timedelta(hours=24):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="reservation_too_far",
                    translation_placeholders=placeholders,
                )
            if max_amps is not None:
                limit = self.data.device.max_amps
                if max_amps > limit:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN,
                        translation_key="max_amps_above_limit",
                        translation_placeholders={**placeholders, "max_amps": str(max_amps), "limit": str(limit)},
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

    async def async_stop_charging(self) -> bool:
        with self._action_errors("stop_failed"):
            return await self.device.stop_charging()

    async def async_set_nickname(self, nickname: str) -> bool:
        """Set device nickname."""
        with self._action_errors():
            return await self.device.set_nickname(nickname)

    async def async_set_max_amps(self, amperage: int) -> bool:
        """Set maximum output amperage."""
        with self._action_errors():
            return await self.device.set_output_amperage(amperage)

    async def async_set_language(self, language: LanguageEnum) -> bool:
        """Set the language of the charger's display."""
        with self._action_errors():
            return await self.device.set_language(language)

    async def async_set_weekly_plan(self, days: list[int], start: time, end: time) -> bool:
        """Charge from start to end on the given weekdays (0 = Monday), as the app does; no days turns it off."""
        # the app's arithmetic: an end before the start runs into the next day, an equal one is 24 h
        duration = (end.hour * 60 + end.minute - start.hour * 60 - start.minute) % 1440 or 1440
        on = WeeklyPlanSlot(enabled=True, start=start, duration_minutes=duration)
        plan = WeeklyPlan(slots=[on if day in days else WeeklyPlanSlot() for day in range(7)])
        with self._action_errors():
            return await self.device.set_weekly_plan(plan)

    async def async_read_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """The charger's stored sessions, newest first."""
        with self._action_errors():
            history = await self.device.read_history()
        oldest = datetime.min.replace(tzinfo=UTC)
        records = sorted(history.items(), key=lambda item: item[1].start_datetime or oldest, reverse=True)
        return [
            {
                "slot": slot,
                **record.model_dump(mode="json"),
                "start_type": record.start_type.name.lower(),
                "stop_reason": record.stop_reason.name.lower(),
            }
            for slot, record in records[:limit]
        ]
