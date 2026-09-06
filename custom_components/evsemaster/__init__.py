"""The EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_ACTION_START_CHARGING,
    SERVICE_DATA_DURATION_HOURS,
    SERVICE_DATA_MAX_AMPS,
    SERVICE_DATA_START_DATETIME,
)
from .coordinator import EVSEMasterDataUpdateCoordinator
from .hub import async_release_listener

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.TEXT,
    Platform.NUMBER,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once; they are shared by every charger."""

    async def start_charge_service_call(service: ServiceCall) -> None:
        coordinators = await _async_target_coordinators(hass, service)
        for coordinator in coordinators:
            await coordinator.async_start_charging(
                service.data.get(SERVICE_DATA_MAX_AMPS),
                service.data.get(SERVICE_DATA_START_DATETIME),
                service.data.get(SERVICE_DATA_DURATION_HOURS),
            )

    hass.services.async_register(DOMAIN, SERVICE_ACTION_START_CHARGING, start_charge_service_call)
    return True


async def _async_target_coordinators(
    hass: HomeAssistant, service: ServiceCall
) -> list[EVSEMasterDataUpdateCoordinator]:
    """Resolve the chargers a service call targets (device, entity or area)."""
    coordinators: list[EVSEMasterDataUpdateCoordinator] = []
    for entry_id in await async_extract_config_entry_ids(service):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
            coordinators.append(entry.runtime_data)
    if not coordinators:
        raise HomeAssistantError("No EVSEMaster charger matched the target of this action")
    return coordinators


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EVSEMaster from a config entry."""

    coordinator = EVSEMasterDataUpdateCoordinator(hass, entry)

    try:
        await coordinator.async_init()
        await coordinator.async_config_entry_first_refresh()
        if not coordinator.unique_id:
            # every entity is named after it, so refuse to build entities we cannot identify
            raise ConfigEntryError(f"EVSE at {coordinator.host} did not report a serial number")
    except ConfigEntryError:
        await coordinator.async_shutdown()
        await async_release_listener(hass)
        raise
    except Exception as err:
        _LOGGER.error("Failed to initialize EVSEMaster: %s", err)
        await coordinator.async_shutdown()
        await async_release_listener(hass)
        raise ConfigEntryNotReady from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # shut down here rather than leaving it to async_on_unload, which runs after this
        # returns - the listener would still see this device and stay bound with nothing to do
        await entry.runtime_data.async_shutdown()
        await async_release_listener(hass)
    return unloaded
