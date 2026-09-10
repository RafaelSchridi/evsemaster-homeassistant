# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

HACS custom integration (domain `evsemaster`, `iot_class: local_push`) for EVSE chargers that use the EVSEMaster app. Integration files live in `custom_components/evsemaster/`; the repo root holds only tests, config and packaging. All protocol work is delegated to the `evsemaster` Python package, developed in the sibling repo `RafaelSchridi/evsemaster`.

To run it, copy or symlink `custom_components/evsemaster/` into a Home Assistant instance.

- Lint/format: `ruff check` / `ruff format` (config in `ruff.toml`, line-length 120)
- Test: `pip install -r requirements_test.txt` then `pytest` from the repo root.
- Tests drive the integration end to end against `evsemaster.testing.FakeEvse` chargers on
  loopback (each on its own `127.0.0.x`), covering setup, two chargers at once, service
  targeting, unload, discovery and the config flow.
- The autouse `loopback_listener` fixture binds the shared listener to `127.0.0.1` on a
  per-test port. Never let the suite bind `0.0.0.0:28376`: it then receives broadcasts from
  real chargers on the network, which race the fakes and win (a real charger's serial showing
  up in the discovery test is the symptom).

## Library loading and dev workflow

Import protocol classes straight from the package: `from evsemaster import EvseStatus`. Only `BaseSchema` is not in the library's `__all__`, so `coordinator.py` takes it from `evsemaster.data_types`.

To develop against unreleased library changes, `pip install -e ../evsemaster` into the venv that runs the tests or Home Assistant. Do not vendor the library into this repo — an `evsemaster` directory next to the integration's modules gets imported a second time as `custom_components.evsemaster.evsemaster`, and the duplicate classes make the coordinator's `isinstance(payload, EvseStatus)` checks fail silently, leaving every entity `unknown` with nothing in the log.

Releases pin the library version in `manifest.json` requirements (`evsemaster==x.y.z`); bump it together with the manifest `version` field.

## Validation

`.github/workflows/ci.yaml` runs the HACS action and hassfest alongside lint and tests; both must stay green and free of `ignore` keys, since [hacs/default](https://github.com/hacs/default) requires links to passing runs. Reproduce hassfest locally with the same mount their CI uses:

```
docker run --rm -v "$PWD/custom_components/evsemaster":/github/workspace/custom_components/evsemaster ghcr.io/home-assistant/hassfest:latest
```

Two of its rules bite easily: `manifest.json` keys must be sorted (`domain`, `name`, then alphabetical), and sensor state values must be lowercase slugs matching the `state` keys in `translations/en.json`.

## Architecture

- `hub.py` — owns the one `EvseListener` (UDP port 28376) shared by every config entry, kept in `hass.data[DOMAIN]` and stopped when the last charger is removed. Chargers without a config entry arrive here as discovery flows.
- `coordinator.py` — `EVSEMasterDataUpdateCoordinator` is one charger. It registers an `EvseDevice` with the shared listener in `async_init` (awaitable, so it cannot happen in `__init__`) and combines push with poll:
  - Push (primary data path, hence `local_push`): protocol `event_callback` → `_on_protocol_event` → `async_set_updated_data`.
  - Poll (60s) is a watchdog: every push goes through `async_set_updated_data`, which restarts the countdown, so it only runs after 60s without a push. It ensures login and re-requests status. Essentials (nickname, configured amps) run on their own 30-minute `async_track_time_interval` timer.
  - `coordinator.data` is a `DataSchema` pydantic model: `status` (`EvseStatus`), `charging_status` (`ChargingStatus`), `device` (`EvseDeviceInfo`).
  - Device identity is `coordinator.unique_id`, which returns `entry.unique_id` and nothing else (the charger serial, backfilled on first login for entries created before multi-device support). It must never fall back to a value that can change: the host moves with DHCP and `data.device.serial_number` defaults to `00000000`, and every entity id is built from this, so a changing value re-registers the whole device as duplicates. Setup fails with `ConfigEntryError` if the first login yields no serial, which is what guarantees it is set before any entity exists.
  - Device name is `model + nickname` (`coordinator.device_name`), re-applied by
    `_async_follow_device_name` on every device-info event: `device_info` is only read when an
    entity is registered, so a nickname set later would otherwise not show until a restart. It
    writes `name`, not `name_by_user`, so a manual rename in the UI still wins. Entity ids are
    slugged once at registration and never follow it.
  - All control actions (start/stop charging, nickname, max amps) run inside `_action_errors`, which turns library refusals into translated errors naming the charger (`display_name`, the user's rename included). Messages live under `exceptions` in `translations/en.json`; a failed stop has its own `stop_failed` message warning the car may still be charging.
- `entity.py` — `EVSEMasterEntity`, the base for every platform: sets `_attr_unique_id` to `f"{coordinator.unique_id}_{_unique_id_key}"` and `_attr_device_info`. Platform classes only declare `_unique_id_key`, `_attr_translation_key` and their value property; state is read from `self.entry` (= `coordinator.data`). Display names come from `translations/en.json` via `_attr_translation_key`.
- `__init__.py` registers the `evsemaster.start_charging` service in `async_setup` (once for the whole integration, not per entry, or a second charger steals the service) and resolves the call's target with `async_extract_config_entry_ids`. Every targeted charger gets the command before anything is raised: one failure is re-raised as is, several are combined into `start_failed`.
- `config_flow.py` — host + password form, plus an `integration_discovery` step that only asks for the password. Validation borrows the shared listener rather than binding its own socket. The entry `unique_id` is the charger serial, so re-running the flow repairs a changed IP.

## Behavior constraints

- `start_charging` service: reservations max 24h in the future; `max_amps` above the user-configured max is clamped to it, above the device hardware max raises an error.
- The library auto-stops an active reservation/completed state before starting a new charge; the integration does not need to handle that.
- Max amps: on a model that applies the amperage only at session start (Telestar EC311S, per the
  library's capability table), the number entity goes **unavailable while charging** and
  `async_set_max_amps` raises `ServiceValidationError` (`unsupported_operation`) rather than swallowing the refusal. The charger
  echoes a mid-charge change back within seconds and then ignores it, so an enabled control would
  display a limit that is not the one being delivered.
- Stop charging: the button stays available with no car connected; pressing it in `NOT_CONNECTED`
  raises `ServiceValidationError` (`nothing_to_stop`) instead. Availability means "charger reachable",
  not "action meaningful": HA skips unavailable entities in service calls without an error.
