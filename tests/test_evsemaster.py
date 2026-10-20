"""End-to-end tests against fake chargers on loopback."""

import asyncio
from datetime import timedelta
from unittest.mock import PropertyMock, patch

import pytest
from evsemaster import CommandEnum, CurrentStateEnum, now_aware
from evsemaster.device import HEADING_TIMEOUT
from evsemaster.testing import FakeEvse, charge_record_payload
from homeassistant.components.logger.helpers import get_integration_loggers
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.evsemaster.const import DOMAIN, WEEKDAYS
from custom_components.evsemaster.coordinator import ESSENTIALS_INTERVAL

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


@pytest.fixture
def entity_registry_enabled_by_default():
    """Register entities that are disabled by default as enabled, so they have a state."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


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
    assert len(ids) == 31, sorted(ids)
    assert all(uid.startswith(f"{SERIAL_A}_") for uid in ids), sorted(ids)
    assert not any("00000000" in uid for uid in ids)

    # values pushed by the charger reached the entities
    assert hass.states.get(ids[f"{SERIAL_A}_current_state"]).state == "ready_to_charge"
    assert hass.states.get(ids[f"{SERIAL_A}_plug_state"]).state == "connected_locked"
    assert hass.states.get(ids[f"{SERIAL_A}_total_kwh"]).state == "1234.56"
    assert hass.states.get(ids[f"{SERIAL_A}_charge_kwh"]).state == "12.34"
    assert hass.states.get(ids[f"{SERIAL_A}_nickname"]).state == "Garage"
    max_amps = hass.states.get(ids[f"{SERIAL_A}_configured_max_amps"])
    assert max_amps.attributes["max"] == 32.0  # hardware limit, not the construction-time default

    device = device_for(hass, entry)
    assert device.identifiers == {(DOMAIN, SERIAL_A)}
    assert (device.manufacturer, device.model) == ("BESEN", "BS20")
    # the login's version string is what the vendor app labels "Firmware version"
    assert (device.sw_version, device.hw_version) == ("1.2.34", None)
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
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": ids[f"{SERIAL_A}_stop_charging_button"]}, blocking=True
        )
    assert err.value.translation_key == "stop_failed"
    assert err.value.translation_placeholders == {"device": "BS20 Garage"}


async def test_stop_without_a_car_is_refused_not_hidden(hass):
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", state=CurrentStateEnum.NOT_CONNECTED).start()
    try:
        entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
        assert ok
        button = entity_ids(hass, entry)[f"{SERIAL_A}_stop_charging_button"]
        assert hass.states.get(button).state != STATE_UNAVAILABLE

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        assert err.value.translation_key == "nothing_to_stop"
        assert err.value.translation_placeholders == {"device": "BS20"}
        assert CommandEnum.CHARGE_STOP_REQUEST not in evse.received
    finally:
        evse.stop()


async def test_start_button_without_a_car_is_refused_not_hidden(hass):
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", state=CurrentStateEnum.NOT_CONNECTED).start()
    try:
        entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
        assert ok
        button = entity_ids(hass, entry)[f"{SERIAL_A}_start_charging_button"]
        assert hass.states.get(button).state != STATE_UNAVAILABLE

        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        assert err.value.translation_key == "no_car_connected"
        assert err.value.translation_placeholders == {"device": "BS20"}
        assert CommandEnum.CHARGE_START_REQUEST not in evse.received
    finally:
        evse.stop()


async def test_controls_go_unavailable_with_the_charger(hass, evse_a):
    """Entities that override availability must still follow a failed poll, not just a status ever seen."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    ids = entity_ids(hass, entry)
    watched = [
        ids[f"{SERIAL_A}_{key}"]
        for key in ("start_charging_button", "stop_charging_button", "configured_max_amps", "current_state")
    ]
    assert all(hass.states.get(e).state != STATE_UNAVAILABLE for e in watched)

    coordinator = entry.runtime_data
    coordinator.device._authenticated = False
    with patch.object(coordinator.device, "login", return_value=False):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert [e for e in watched if hass.states.get(e).state != STATE_UNAVAILABLE] == []


async def test_live_sensors_go_stale_when_the_charger_stops_reporting(hass, evse_a):
    """A charger that stopped heading still takes commands, so controls stay, but its last snapshot is not current."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    ids = entity_ids(hass, entry)
    coordinator = entry.runtime_data

    evse_a.end_session()
    coordinator.device._last_heading = now_aware() - HEADING_TIMEOUT
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    for key in ("current_power", "current_state", "plug_state_binary", "charging_binary"):
        assert hass.states.get(ids[f"{SERIAL_A}_{key}"]).state == STATE_UNAVAILABLE, key
    for key in ("stop_charging_button", "start_charging_button", "configured_max_amps", "nickname"):
        assert hass.states.get(ids[f"{SERIAL_A}_{key}"]).state != STATE_UNAVAILABLE, key
    assert hass.states.get(ids[f"{SERIAL_A}_total_kwh"]).state == "1234.56"


async def test_unmapped_states_read_as_unknown_without_hiding_stop(hass):
    """Firmware states we cannot map must not be guessed at, and must not disarm the stop button."""
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", state=200, plug=16).start()
    try:
        entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
        assert ok
        ids = entity_ids(hass, entry)

        for key in ("current_state", "plug_state", "plug_state_binary", "charging_binary"):
            assert hass.states.get(ids[f"{SERIAL_A}_{key}"]).state == STATE_UNKNOWN, key
        assert hass.states.get(ids[f"{SERIAL_A}_stop_charging_button"]).state != STATE_UNAVAILABLE
    finally:
        evse.stop()


async def test_a_cancelled_reservation_stops_being_reported(hass, evse_a):
    """A Telestar keeps reporting a cancelled reservation forever; the values below are from its logs."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    coordinator = entry.runtime_data
    ids = entity_ids(hass, entry)
    start = ids[f"{SERIAL_A}_reservation_datetime"]
    duration = ids[f"{SERIAL_A}_reservation_max_duration"]

    pending = coordinator.data.charging_status.model_copy(
        update={
            "current_state": CurrentStateEnum.CHARGING_RESERVATION,
            "reservation_datetime": dt_util.parse_datetime("2026-09-17T09:30:00+02:00"),
            "max_duration_minutes": 480,
        }
    )
    coordinator._on_protocol_event("ChargingStatus", pending)
    await hass.async_block_till_done()
    assert hass.states.get(duration).state == "480"
    assert hass.states.get(start).state != STATE_UNKNOWN

    # stop pressed: the charger reports the same reservation with the car still plugged in
    cancelled = pending.model_copy(update={"current_state": CurrentStateEnum.READY_TO_CHARGE})
    coordinator._on_protocol_event("ChargingStatus", cancelled)
    await hass.async_block_till_done()
    assert hass.states.get(duration).state == STATE_UNKNOWN, "a cancelled reservation kept its duration"
    assert hass.states.get(start).state == STATE_UNKNOWN, "a cancelled reservation kept its start time"


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
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "start_charging", {"device_id": "does-not-exist"}, blocking=True)
    assert err.value.translation_key == "no_matching_charger"


async def test_errors_name_the_charger_as_the_user_sees_it(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    device = device_for(hass, entry)
    dr.async_get(hass).async_update_device(device.id, name_by_user="Driveway")

    too_far = (dt_util.now() + timedelta(hours=25)).isoformat()
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "start_charging", {"device_id": device.id, "start_datetime": too_far}, blocking=True
        )
    assert err.value.translation_key == "reservation_too_far"
    assert err.value.translation_placeholders == {"device": "Driveway"}
    assert CommandEnum.CHARGE_START_REQUEST not in evse_a.received


async def test_start_charging_reaches_every_charger_before_reporting_a_failure(hass, evse_a, evse_b):
    entry_a, _ = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A, title="A")
    entry_b, _ = await add_entry(hass, "127.0.0.2", unique_id=SERIAL_B, title="B")
    targets = {"device_id": [device_for(hass, entry_a).id, device_for(hass, entry_b).id]}

    # one charger down: the other still starts, and the error is that charger's own
    entry_a.runtime_data.device._authenticated = False
    evse_b.received.clear()
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(DOMAIN, "start_charging", targets, blocking=True)
    assert err.value.translation_key == "not_responding"
    assert err.value.translation_placeholders == {"device": "BS20 Garage"}
    assert await until(hass, lambda: CommandEnum.CHARGE_START_REQUEST in evse_b.received), "B was skipped"

    # both down: one error that names each (also proves the messages render from en.json)
    entry_b.runtime_data.device._authenticated = False
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(DOMAIN, "start_charging", targets, blocking=True)
    assert err.value.translation_key == "action_failed"
    assert "BS20 Garage" in str(err.value) and "BS20 Carport" in str(err.value)


async def test_last_seen_sensor_is_a_disabled_diagnostic(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    entity = er.async_get(hass).async_get(entity_ids(hass, entry)[f"{SERIAL_A}_last_alive"])
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity.entity_category is EntityCategory.DIAGNOSTIC


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

    # the charger dropped our registration and stopped heading us
    evse_a.stop()
    # both, so this holds against the pinned library and the unreleased one alike
    device._last_alive = None
    device._last_heading = None
    device._last_login_attempt = None  # as if the login cooldown had elapsed
    await asyncio.sleep(0.5)
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


async def test_announcements_do_not_postpone_the_watchdog(hass, evse_a):
    """A charger that dropped us only announces itself; the poll must still run to wake it."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    coordinator = entry.runtime_data

    with (
        patch.object(coordinator, "async_set_updated_data", wraps=coordinator.async_set_updated_data) as pushed,
        patch.object(coordinator, "async_update_listeners", wraps=coordinator.async_update_listeners) as refreshed,
    ):
        evse_a.end_session()
        await settle(hass, 2.0)

    assert refreshed.called, "announcements no longer reach the entities"
    assert not pushed.called, "an announcement restarted the watchdog countdown"


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
    """Nickname and configured amps are re-read every 30 minutes, even while pushes keep the poll asleep."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok

    # the poll no longer carries them
    evse_a.received.clear()
    await entry.runtime_data.async_refresh()
    await settle(hass)
    assert CommandEnum.NICKNAME_REQUEST not in evse_a.received

    async_fire_time_changed(hass, dt_util.utcnow() + ESSENTIALS_INTERVAL + timedelta(seconds=1))
    await settle(hass)
    assert CommandEnum.NICKNAME_REQUEST in evse_a.received
    assert CommandEnum.OUTPUT_AMPERAGE_REQUEST in evse_a.received


async def test_debug_logging_reaches_the_library(hass):
    """The debug toggle must cover evsemaster.*, where the protocol logs live."""
    integration = await async_get_integration(hass, DOMAIN)
    assert "evsemaster" in await get_integration_loggers(hass, DOMAIN), integration.loggers


async def test_a_user_rename_survives_a_nickname_change(hass, evse_a):
    """The registry follows the charger's nickname, but never overwrites a name the user set."""
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    registry = dr.async_get(hass)
    device = device_for(hass, entry)
    assert device.name == "BS20 Garage"

    registry.async_update_device(device.id, name_by_user="Rafael's charger")
    await hass.async_block_till_done()

    evse_a.nickname = "Driveway"
    async_fire_time_changed(hass, dt_util.utcnow() + ESSENTIALS_INTERVAL + timedelta(seconds=1))
    await settle(hass)

    device = device_for(hass, entry)
    assert device.name == "BS20 Driveway", "the integration should still follow the charger"
    assert device.name_by_user == "Rafael's charger", "a user rename must not be overwritten"
    # and the user's name is what the entities actually display
    ids = entity_ids(hass, entry)
    assert hass.states.get(ids[f"{SERIAL_A}_current_state"]).name == "Rafael's charger Current State"


async def test_the_fault_sensor_names_every_fault(hass):
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", errors=1 << 25 | 1).start()
    try:
        entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
        assert ok
        fault = entity_ids(hass, entry)[f"{SERIAL_A}_fault"]
        assert hass.states.get(fault).state == "emergency_stop"
        assert hass.states.get(fault).attributes["faults"] == ["emergency_stop", "metering_module_failure"]

        evse.errors = 0
        await entry.runtime_data.device.request_status()
        assert await until(hass, lambda: hass.states.get(fault).state == "none")
        assert hass.states.get(fault).attributes["faults"] == []
    finally:
        evse.stop()


async def test_the_language_select_sets_the_charger(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    select = entity_ids(hass, entry)[f"{SERIAL_A}_language"]
    assert hass.states.get(select).state == "english"

    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "german"}, blocking=True)
    assert await until(hass, lambda: hass.states.get(select).state == "german")
    assert evse_a.language == 3


async def test_a_nickname_the_charger_would_not_show_is_refused(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    nickname = entity_ids(hass, entry)[f"{SERIAL_A}_nickname"]
    assert hass.states.get(nickname).attributes["max"] == 11
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call("text", "set_value", {"entity_id": nickname, "value": "Garáž"}, blocking=True)
    assert err.value.translation_key == "invalid_value"


async def test_last_session_sensors_are_disabled_by_default(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    ids = entity_ids(hass, entry)
    registry = er.async_get(hass)
    for key in ("end", "stop_reason"):
        entity = registry.async_get(ids[f"{SERIAL_A}_last_session_{key}"])
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_a_finished_session_fills_last_session_and_survives_a_reload(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    ids = entity_ids(hass, entry)
    end_id = ids[f"{SERIAL_A}_last_session_end"]
    stop_reason_id = ids[f"{SERIAL_A}_last_session_stop_reason"]
    assert hass.states.get(end_id).state == STATE_UNKNOWN

    evse_a.upload_record(charge_record_payload(charge_id="Clock 1792140720", stop_reason=17))
    assert await until(hass, lambda: hass.states.get(end_id).state != STATE_UNKNOWN)
    assert CommandEnum.UPLOAD_LOCAL_CHARGE_RECORD_RESPONSE in evse_a.received, "the record was not acknowledged"
    assert hass.states.get(stop_reason_id).state == "unplugged"
    end = hass.states.get(end_id)
    assert end.attributes["charge_id"] == "Clock 1792140720"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await settle(hass)
    assert hass.states.get(end_id).state == end.state, "the last session was lost on a reload"
    assert hass.states.get(stop_reason_id).state == "unplugged"


async def test_charge_history_returns_records_newest_first(hass, monkeypatch):
    monkeypatch.setattr("evsemaster.device.HISTORY_REQUEST_INTERVAL", 0.01)
    monkeypatch.setattr("evsemaster.device.HISTORY_REPLY_WAIT", 0.2)
    history = {
        1: charge_record_payload("older", start=1_790_000_000),
        2: charge_record_payload("newest", start=1_792_000_000),
        4: charge_record_payload("oldest", start=1_780_000_000),
    }
    evse = await FakeEvse(SERIAL_A, ip="127.0.0.1", history=history, history_capacity=5).start()
    try:
        entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
        assert ok
        response = await hass.services.async_call(
            DOMAIN,
            "get_charge_history",
            {"device_id": device_for(hass, entry).id},
            blocking=True,
            return_response=True,
        )
        records = response[SERIAL_A]["records"]
        assert [(record["slot"], record["charge_id"]) for record in records] == [
            (2, "newest"),
            (1, "older"),
            (4, "oldest"),
        ]
        assert response[SERIAL_A]["unread_slots"] == []
        assert records[0]["stop_reason"] == "client"
        assert records[0]["start_type"] == "client"
    finally:
        evse.stop()


async def test_set_weekly_plan_writes_the_days_and_the_sensor_follows(hass, evse_a):
    entry, ok = await add_entry(hass, "127.0.0.1", unique_id=SERIAL_A)
    assert ok
    plan = entity_ids(hass, entry)[f"{SERIAL_A}_weekly_plan"]
    assert hass.states.get(plan).state == "off"

    await hass.services.async_call(
        DOMAIN,
        "set_weekly_plan",
        {
            "device_id": device_for(hass, entry).id,
            "days": ["monday", "friday"],
            "start_time": "22:00:00",
            "end_time": "06:00:00",
        },
        blocking=True,
    )
    assert await until(hass, lambda: hass.states.get(plan).state == "on")
    # an end before the start runs into the next day, as in the app
    window = {"start": "22:00", "duration_minutes": 480}
    assert {k: v for k, v in hass.states.get(plan).attributes.items() if k in WEEKDAYS} == {
        "monday": window,
        "friday": window,
    }
    written = evse_a.weekly_plan
    assert written[0:9] == bytes.fromhex("03 16 00 01e0 ffffffff")
    assert written[9:18] == bytes.fromhex("01 00 00 0000 ffffffff")

    await hass.services.async_call(
        DOMAIN,
        "set_weekly_plan",
        {"device_id": device_for(hass, entry).id, "start_time": "00:00:00", "end_time": "00:00:00"},
        blocking=True,
    )
    assert await until(hass, lambda: hass.states.get(plan).state == "off"), "no days did not turn the plan off"
