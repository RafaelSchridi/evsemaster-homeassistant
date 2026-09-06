"""The UDP listener shared by every EVSEMaster config entry.

One socket serves all chargers; packets are routed to a device by its serial. Chargers we do
not have a config entry for surface as discovery flows.
"""

from __future__ import annotations

import logging

from evsemaster import EvseListener
from homeassistant.components import network
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ListenerError(HomeAssistantError):
    """The shared listener could not be started."""


async def async_get_listener(hass: HomeAssistant) -> EvseListener:
    """Return the shared listener, starting it on first use."""
    listener: EvseListener | None = hass.data.get(DOMAIN)
    if listener:
        return listener

    listener = EvseListener(on_discovery=lambda discovered: _async_on_discovery(hass, discovered))
    if not await listener.start():
        raise ListenerError(f"Could not listen on UDP port {listener.listen_port}")
    hass.data[DOMAIN] = listener
    await _async_probe(hass, listener)
    return listener


async def async_release_listener(hass: HomeAssistant) -> None:
    """Stop the listener once the last device is gone."""
    listener: EvseListener | None = hass.data.get(DOMAIN)
    if listener and not listener.devices:
        await listener.stop()
        hass.data.pop(DOMAIN, None)
        _LOGGER.debug("Stopped the EVSE listener, no devices left")


@callback
def _async_on_discovery(hass: HomeAssistant, discovered) -> None:
    """Start a discovery flow for a charger we do not manage."""
    _LOGGER.info("Discovered EVSE %s at %s", discovered.serial_number, discovered.host)
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovered.model_dump(),
        )
    )


async def _async_probe(hass: HomeAssistant, listener: EvseListener) -> None:
    """Ask chargers that are not broadcasting to announce themselves."""
    try:
        addresses = await network.async_get_ipv4_broadcast_addresses(hass)
    except Exception as err:  # network integration is best-effort here
        _LOGGER.debug("Could not determine broadcast addresses: %s", err)
        return
    for address in addresses:
        await listener.probe(str(address))
