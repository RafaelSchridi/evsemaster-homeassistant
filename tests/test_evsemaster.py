"""End-to-end tests against fake chargers on loopback."""

import asyncio
from datetime import timedelta

import pytest
from custom_components.evsemaster.const import DOMAIN
from custom_components.evsemaster.coordinator import ESSENTIALS_INTERVAL
from homeassistant.components.logger.helpers import get_integration_loggers
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from pytest_homeassistant_custom_component.common import MockConfigEntry

from evsemaster import CommandEnum
from evsemaster.testing import FakeEvse

SERIAL_A = "aa" * 8
SERIAL_B = "bb" * 8


async def settle(hass, seconds=1.0):
    """Let UDP round trips to the fake chargers complete.

    async_block_till_done only drains HA's own tasks, not datagrams in flight to sockets
    that HA does not own.
    """
    for _ in range(int(seconds / 0.05)):
        await asyncio.sleep(0.05)
    await hass.async_block_till_done()


async def until(hass, predicate, seconds=5.0):
    """Wait for a condition that depends on packets arriving."""
    for _ in range(int(seconds / 0.05)):
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()
        if predicate():
            return True
    return False


def device_for(hass, entry):
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1, devices
    return devices[0]


def entity_ids(hass, entry):
    registry = er.async_get(hass)
    return {e.unique_id: e.entity_id for e in registry.entities.values() if e.config_entry_id == entry.entry_id}


async def add_entry(hass, host, password="123456", unique_id=None, title="EVSE"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PASSWORD: password},
        unique_id=unique_id,
        title=title,
    )
    entry.add_to_hass(hass)
    ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if ok:
        await settle(hass)
    return entry, ok


@pytest.fixture
async def evse_a():
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", nickname="Garage").start()
    yield evse
    evse.stop()


@pytest.fixture
async def evse_b():
    evse = await FakeEvse(SERIAL_B, ip="127.0.0.2", three_phase=False, nickname="Carport").start()
    yield evse
    evse.stop()


async def test_single_charger_sets_up_with_entities(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok and entry.state is ConfigEntryState.LOADED

    coordinator = entry.runtime_data
    assert coordinator.device.is_logged_in
    assert coordinator.device.serial == SERIAL_A
    # the send port was learned from the charger, not assumed
    assert coordinator.device.send_port == evse_a.port

    ids = entity_ids(hass, entry)
    assert len(ids) == 25, sorted(ids)
    assert all(uid.startswith(f"{SERIAL_A}_") for uid in ids), sorted(ids)
    assert not any("00000000" in uid for uid in ids)

    # values pushed by the charger reached the entities
    assert hass.states.get(ids[f"{SERIAL_A}_current_state"]).state == "READY_TO_CHARGE"
    assert hass.states.get(ids[f"{SERIAL_A}_plug_state"]).state == "CONNECTED_LOCKED"
    assert hass.states.get(ids[f"{SERIAL_A}_total_kwh"]).state == "1234.56"
    assert hass.states.get(ids[f"{SERIAL_A}_charge_kwh"]).state == "12.34"
    assert hass.states.get(ids[f"{SERIAL_A}_nickname"]).state == "Garage"
    max_amps = hass.states.get(ids[f"{SERIAL_A}_configured_max_amps"])
    assert max_amps.attributes["max"] == 32.0  # hardware limit, not the construction-time default

    device = device_for(hass, entry)
    assert device.identifiers == {(DOMAIN, SERIAL_A)}
    assert (device.manufacturer, device.model) == ("BESEN", "BS20")
    # the registry follows model and nickname, which land after the device is created
    assert device.name == "BS20 Garage"
    # has_entity_name prefixes it, so the device name is what every friendly name carries
    assert hass.states.get(ids[f"{SERIAL_A}_current_state"]).name == "BS20 Garage Current State"


async def test_a_failing_stop_surfaces_in_home_assistant(hass, evse_a):
    """A stop that cannot be sent must raise, not quietly do nothing to a charging car."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    ids = entity_ids(hass, entry)

    entry.runtime_data.device._authenticated = False  # session lost since the last poll
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": ids[f"{SERIAL_A}_stop_charging_button"]}, blocking=True
        )


async def test_single_phase_charger_reports_status(hass, evse_b):
    entry, ok = await add_entry(hass, "127.0.0.2", unique_id=SERIAL_B)
    assert ok
    status = entry.runtime_data.data.status
    assert status is not None, "single-phase status was dropped"
    assert status.l1_voltage == 230.1
    assert (status.l2_voltage, status.l3_voltage) == (0.0, 0.0)


async def test_two_chargers_are_independent(hass, evse_a, evse_b):
    entry_a, ok_a = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A, title="A")
    entry_b, ok_b = await add_entry(hass, "127.0.0.2", unique_id=SERIAL_B, title="B")
    assert ok_a and ok_b

    # one socket for both
    listener = hass.data[DOMAIN]
    assert len(listener.devices) == 2
    assert listener.get_device(SERIAL_A) is entry_a.runtime_data.device
    assert listener.get_device(SERIAL_B) is entry_b.runtime_data.device

    # no crossover: each device only ever saw its own serial
    assert entry_a.runtime_data.data.device.serial_number == SERIAL_A
    assert entry_b.runtime_data.data.device.serial_number == SERIAL_B
    assert entry_a.runtime_data.data.device.nickname == "Garage"
    assert entry_b.runtime_data.data.device.nickname == "Carport"
    assert device_for(hass, entry_a).name == "BS20 Garage"
    assert device_for(hass, entry_b).name == "BS20 Carport"

    a_ids = set(entity_ids(hass, entry_a))
    b_ids = set(entity_ids(hass, entry_b))
    assert a_ids and b_ids and not (a_ids & b_ids)

    # a service targeting B must not touch A
    device_b = device_for(hass, entry_b)
    assert device_b.identifiers == {(DOMAIN, SERIAL_B)}
    evse_a.received.clear()
    evse_b.received.clear()
    await hass.services.async_call(DOMAIN, "start_charging", {"device_id": device_b.id, "max_amps": 10}, blocking=True)
    assert await until(hass, lambda: CommandEnum.CHARGE_START_REQUEST in evse_b.received)
    assert CommandEnum.CHARGE_START_REQUEST not in evse_a.received


async def test_service_without_a_matching_target_errors(hass, evse_a):
    await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    with pytest.raises(Exception) as err:
        await hass.services.async_call(DOMAIN, "start_charging", {"device_id": "does-not-exist"}, blocking=True)
    assert "EVSEMaster" in str(err.value) or "not found" in str(err.value).lower()


async def test_unload_releases_the_socket(hass, evse_a):
    entry, _ = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert DOMAIN in hass.data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass.data, "listener kept running with no devices"

    # the port is free again, so a reload can bind it
    reloaded = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert reloaded and entry.runtime_data.device.is_logged_in


async def test_legacy_entry_gets_its_unique_id_backfilled(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=None)
    assert ok
    assert entry.unique_id == SERIAL_A
    assert all(uid.startswith(f"{SERIAL_A}_") for uid in entity_ids(hass, entry))


async def test_session_recovers_from_a_broadcast(hass, evse_a):
    entry, _ = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    device = entry.runtime_data.device

    # the charger dropped our session and stopped sending headings
    evse_a.stop()
    device._last_heading = None
    assert not device.is_logged_in

    evse_a2 = await FakeEvse(SERIAL_A, ip="127.0.0.1", nickname="Garage").start()
    try:
        evse_a2.announce()
        for _ in range(50):
            await asyncio.sleep(0.05)
            if device.is_logged_in:
                break
        assert device.is_logged_in, "no automatic re-login after the charger announced itself"
        assert device.send_port == evse_a2.port, "did not follow the charger to its new port"
    finally:
        evse_a2.stop()


async def test_unknown_charger_starts_a_discovery_flow(hass, evse_a):
    await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)

    stranger = await FakeEvse("cc" * 8, ip="127.0.0.3", nickname="Garage").start()
    try:
        stranger.announce()
        for _ in range(50):
            await asyncio.sleep(0.05)
            flows = [f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN]
            if flows:
                break
        assert flows, "no discovery flow for an unmanaged charger"
        flow = flows[0]
        assert flow["context"]["source"] == SOURCE_INTEGRATION_DISCOVERY
        assert flow["context"]["unique_id"] == "cc" * 8
        assert flow["context"]["title_placeholders"]["name"] == "BESEN BS20"

        # confirming it only asks for the password
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], None)
        assert result["step_id"] == "discovery_confirm"
        assert set(result["data_schema"].schema) == {CONF_PASSWORD}

        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_PASSWORD: "123456"})
        await hass.async_block_till_done()
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_HOST: "127.0.0.3", CONF_PASSWORD: "123456"}
        assert result["title"] == f"BESEN BS20 ({'cc' * 8})"
    finally:
        stranger.stop()


async def test_user_flow_sets_unique_id_and_rejects_duplicates(hass, evse_a):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PASSWORD: "123456"}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == SERIAL_A

    # same charger again: aborts instead of creating a second entry
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PASSWORD: "123456"}
    )
    assert result["type"] == "abort" and result["reason"] == "already_configured"


async def test_wrong_password_is_reported_as_invalid_auth(hass, evse_a):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PASSWORD: "000000"}
    )
    assert result["type"] == "form" and result["errors"] == {"base": "invalid_auth"}


async def test_essentials_are_refreshed_on_the_long_interval(hass, evse_a):
    """Nickname and configured amps are re-read every 30 minutes, not only at login."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    coordinator = entry.runtime_data

    # a poll before the interval elapses must not re-request them
    evse_a.received.clear()
    await coordinator.async_refresh()
    await settle(hass)
    assert CommandEnum.NICKNAME_REQUEST not in evse_a.received

    coordinator._essentials_refreshed -= ESSENTIALS_INTERVAL + timedelta(seconds=1)
    await coordinator.async_refresh()
    await settle(hass)

    assert CommandEnum.NICKNAME_REQUEST in evse_a.received
    assert CommandEnum.OUTPUT_AMPERAGE_REQUEST in evse_a.received
    # and the timer resets, so it does not then fire on every poll
    evse_a.received.clear()
    await coordinator.async_refresh()
    await settle(hass)
    assert CommandEnum.NICKNAME_REQUEST not in evse_a.received


async def test_debug_logging_reaches_the_library(hass):
    """The debug toggle must cover evsemaster.*, where the protocol logs live."""
    integration = await async_get_integration(hass, DOMAIN)
    assert "evsemaster" in await get_integration_loggers(hass, DOMAIN), integration.loggers
