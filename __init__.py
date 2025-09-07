"""The EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import EVSEMasterDataUpdateCoordinator
from .const import DOMAIN,SERVICE_ACTION_START_CHARGING, SERVICE_DATA_DURATION_HOURS, SERVICE_DATA_MAX_AMPS, SERVICE_DATA_START_DATETIME

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.TEXT,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EVSEMaster from a config entry."""

    coordinator = EVSEMasterDataUpdateCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to initialize EVSEMaster: %s", err)
        raise ConfigEntryNotReady from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # init start/stop service actions
    async def start_charge_service_call(service: ServiceCall) -> bool:
        device_id = service.data.get("device_id")
        #TODO: figure out how to get current device_id to validate againt incoming device_id
        max_amps = service.data.get(SERVICE_DATA_MAX_AMPS)
        duration_hours = service.data.get(SERVICE_DATA_DURATION_HOURS)
        start_datetime = service.data.get(SERVICE_DATA_START_DATETIME)
        success = await coordinator.async_start_charging(max_amps, start_datetime, duration_hours)
        if not success:
            raise Exception("Failed to start charging")
        return success
    
    hass.services.async_register(DOMAIN, SERVICE_ACTION_START_CHARGING, start_charge_service_call)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()


    return unload_ok
