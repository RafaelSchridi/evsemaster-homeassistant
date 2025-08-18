"""Button platform for EVSEMaster integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EVSEMasterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: EVSEMasterDataUpdateCoordinator = entry.runtime_data

    entities = []

    for evse_serial, evse_data in coordinator.data.items():
        entities.extend(
            [
                EVSEStartChargingButton(coordinator, evse_serial),
                EVSEStopChargingButton(coordinator, evse_serial),
                EVSERefreshButton(coordinator, evse_serial),
            ]
        )

    async_add_entities(entities)


class EVSEBaseButton(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Base class for EVSE buttons."""

    def __init__(
        self,
        coordinator: EVSEMasterDataUpdateCoordinator,
        evse_serial: str,
        button_type: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.evse_serial = evse_serial
        self.button_type = button_type

        evse_data = coordinator.data.get(evse_serial, {})
        info = evse_data.get("info", {})
        brand = info.get("brand", "Unknown")
        model = info.get("model", "EVSE")

        self._attr_device_info = {
            "identifiers": {(DOMAIN, evse_serial)},
            "name": f"{brand} {model}",
            "manufacturer": brand,
            "model": model,
            "serial_number": evse_serial,
        }

    @property
    def evse_data(self) -> dict:
        """Get EVSE data from coordinator."""
        return self.coordinator.data.get(self.evse_serial, {})


class EVSEStartChargingButton(EVSEBaseButton, ButtonEntity):
    """Button to start charging."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, evse_serial, "start_charging")
        self._attr_unique_id = f"{evse_serial}_start_charging_button"
        self._attr_name = "Start Charging"
        self._attr_icon = "mdi:play"

    @property
    def available(self) -> bool:
        """Return true if button is available."""
        # Only available if EVSE is online, logged in, and not charging
        meta_state = self.evse_data.get("metaState")
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
            and meta_state != "CHARGING"
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            # Get configured max electricity or default to 16A
            config = self.evse_data.get("config", {})
            max_amps = config.get("maxElectricity", 16)

            success = await self.coordinator.async_start_charging(
                self.evse_serial, max_amps
            )
            if success:
                await self.coordinator.async_request_refresh()
                _LOGGER.info("Started charging on %s", self.evse_serial)
            else:
                _LOGGER.error("Failed to start charging on %s", self.evse_serial)
        except Exception as err:
            _LOGGER.error("Error starting charging on %s: %s", self.evse_serial, err)


class EVSEStopChargingButton(EVSEBaseButton, ButtonEntity):
    """Button to stop charging."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, evse_serial, "stop_charging")
        self._attr_unique_id = f"{evse_serial}_stop_charging_button"
        self._attr_name = "Stop Charging"
        self._attr_icon = "mdi:stop"

    @property
    def available(self) -> bool:
        """Return true if button is available."""
        # Only available if EVSE is online, logged in, and charging
        meta_state = self.evse_data.get("metaState")
        return (
            self.evse_data.get("isOnline", False)
            and self.evse_data.get("isLoggedIn", False)
            and meta_state == "CHARGING"
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            success = await self.coordinator.async_stop_charging(self.evse_serial)
            if success:
                await self.coordinator.async_request_refresh()
                _LOGGER.info("Stopped charging on %s", self.evse_serial)
            else:
                _LOGGER.error("Failed to stop charging on %s", self.evse_serial)
        except Exception as err:
            _LOGGER.error("Error stopping charging on %s: %s", self.evse_serial, err)


class EVSERefreshButton(EVSEBaseButton, ButtonEntity):
    """Button to refresh EVSE data."""

    def __init__(
        self, coordinator: EVSEMasterDataUpdateCoordinator, evse_serial: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, evse_serial, "refresh")
        self._attr_unique_id = f"{evse_serial}_refresh_button"
        self._attr_name = "Refresh"
        self._attr_icon = "mdi:refresh"

    @property
    def available(self) -> bool:
        """Return true if button is available."""
        # Always available if EVSE is online
        return self.evse_data.get("isOnline", False)

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Refreshed data for %s", self.evse_serial)
        except Exception as err:
            _LOGGER.error("Error refreshing data for %s: %s", self.evse_serial, err)
