"""Config flow for the EVSEMaster integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .evse_loader import listener as listener_module
from .hub import ListenerError, async_get_listener, async_release_listener

DeviceAlreadyRegistered = listener_module.DeviceAlreadyRegistered

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_PASSWORD_DATA_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Log in to the charger and return what identifies it.

    Uses the shared listener: a second socket on the same port would steal packets from the
    chargers that are already set up.
    """
    host = data[CONF_HOST]
    password = data[CONF_PASSWORD]

    if not host or not password:
        raise InvalidAuth

    try:
        listener = await async_get_listener(hass)
    except ListenerError as err:
        raise CannotConnect from err

    added = False
    try:
        try:
            device = await listener.async_add_device(host, password)
            added = True
        except DeviceAlreadyRegistered as err:
            # already set up: reuse its session instead of fighting it for the same packets
            device = err.device

        if not device.is_logged_in and not await device.login():
            # a reachable charger announces itself even when the password is wrong, so having
            # its device info tells the two failures apart
            if device.get_latest_device_info():
                raise InvalidAuth
            raise CannotConnect

        info = device.get_latest_device_info()
        if not info or not device.serial:
            raise CannotConnect
        return {
            "serial": device.serial,
            "title": info.nickname or f"{info.brand} {info.model} ({device.serial})".strip(),
        }
    finally:
        if added:
            await listener.async_remove_device(device)
        await async_release_listener(hass)


class EVSEMasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EVSEMaster."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["serial"])
                # re-running the flow for a known charger repairs a changed IP address
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_integration_discovery(self, discovery_info: dict[str, Any]) -> config_entries.ConfigFlowResult:
        """Handle a charger that announced itself on the network."""
        self._discovered = discovery_info
        await self.async_set_unique_id(discovery_info["serial_number"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info["host"]})

        name = " ".join(filter(None, (discovery_info.get("brand"), discovery_info.get("model"))))
        self.context["title_placeholders"] = {
            "name": name or discovery_info["serial_number"],
            "host": discovery_info["host"],
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask only for the password; host and serial come from the announcement."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_HOST: self._discovered["host"], CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                info = await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=STEP_PASSWORD_DATA_SCHEMA,
            description_placeholders=self.context.get("title_placeholders", {}),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
