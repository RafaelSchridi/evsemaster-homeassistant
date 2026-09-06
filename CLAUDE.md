# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

HACS custom integration (domain `evsemaster`, `iot_class: local_push`) for EVSE chargers that use the EVSEMaster app. Integration files live at the repo root (`content_in_root: true` in `hacs.json`). All protocol work is delegated to the `evsemaster` Python package, developed in the sibling repo `RafaelSchridi/evsemaster`.

To run it, place the repo in a Home Assistant instance as `custom_components/evsemaster/`.

- Lint/format: `ruff check` / `ruff format` (config in `ruff.toml`, line-length 120)
- Test: `pip install -r requirements_test.txt` then **`pytest tests`** — the path argument matters.
  `tests/pytest.ini` (not a root one) is what makes `tests/` the rootdir; with the rootdir at the
  repo root, pytest treats the integration's own `__init__.py` as a package to import and every
  test errors. `tests/conftest.py` symlinks the repo into a temp `custom_components/evsemaster`
  so Home Assistant can load it under the name it expects.
- Tests drive the integration end to end against `evsemaster.testing.FakeEvse` chargers on
  loopback (each on its own `127.0.0.x`), covering setup, two chargers at once, service
  targeting, unload, discovery and the config flow.
- The autouse `loopback_listener` fixture binds the shared listener to `127.0.0.1` on a
  per-test port. Never let the suite bind `0.0.0.0:28376`: it then receives broadcasts from
  real chargers on the network, which race the fakes and win (a real charger's serial showing
  up in the discovery test is the symptom).

## Library loading and dev workflow

`evse_loader.py` imports from a local `./evsemaster` package directory first (development), falling back to the installed PyPI package (release). To test unreleased library changes inside HA, copy or symlink `../evsemaster/evsemaster/` into this repo. All modules must import protocol classes via `from .evse_loader import data_types, device, listener` — never import `evsemaster` directly, or the local-first fallback breaks.

That symlink loads the library a *second* time, as `custom_components.evsemaster.evsemaster`, so its classes are not the classes of the top-level `evsemaster` the tests import. `tests/conftest.py` aliases the two in `sys.modules` (`_dedupe_library`); without it the coordinator's `isinstance(payload, EvseStatus)` checks quietly fail and every entity stays `unknown`, with nothing in the log to say why. Run the suite both with and without the symlink before a release — the release path is the one users get.

Releases pin the library version in `manifest.json` requirements (`evsemaster==x.y.z`); bump it together with the manifest `version` field.

## Architecture

- `hub.py` — owns the one `EvseListener` (UDP port 28376) shared by every config entry, kept in `hass.data[DOMAIN]` and stopped when the last charger is removed. Chargers without a config entry arrive here as discovery flows.
- `coordinator.py` — `EVSEMasterDataUpdateCoordinator` is one charger. It registers an `EvseDevice` with the shared listener in `async_init` (awaitable, so it cannot happen in `__init__`) and combines push with poll:
  - Push (primary data path, hence `local_push`): protocol `event_callback` → `_on_protocol_event` → `async_set_updated_data`.
  - Poll (60s): only ensures connect/login and re-requests status; a secondary 30-minute timer refreshes device essentials (nickname, configured amps).
  - `coordinator.data` is a `DataSchema` pydantic model: `status` (`EvseStatus`), `charging_status` (`ChargingStatus`), `device` (`EvseDeviceInfo`).
  - Device identity is `coordinator.unique_id`, which returns `entry.unique_id` and nothing else (the charger serial, backfilled on first login for entries created before multi-device support). It must never fall back to a value that can change: the host moves with DHCP and `data.device.serial_number` defaults to `00000000`, and every entity id is built from this, so a changing value re-registers the whole device as duplicates. Setup fails with `ConfigEntryError` if the first login yields no serial, which is what guarantees it is set before any entity exists.
  - Device name is `model + nickname` (`coordinator.device_name`), re-applied by
    `_async_follow_device_name` on every device-info event: `device_info` is only read when an
    entity is registered, so a nickname set later would otherwise not show until a restart. It
    writes `name`, not `name_by_user`, so a manual rename in the UI still wins. Entity ids are
    slugged once at registration and never follow it.
  - All control actions (start/stop charging, nickname, max amps) go through `async_*` wrappers on the coordinator that validate and translate errors to `HomeAssistantError`.
- `entity.py` — `EVSEMasterEntity`, the base for every platform: sets `_attr_unique_id` to `f"{coordinator.unique_id}_{_unique_id_key}"` and `_attr_device_info`. Platform classes only declare `_unique_id_key`, `_attr_translation_key` and their value property; state is read from `self.entry` (= `coordinator.data`). Display names come from `translations/en.json` via `_attr_translation_key`.
- `__init__.py` registers the `evsemaster.start_charging` service in `async_setup` (once for the whole integration, not per entry, or a second charger steals the service) and resolves the call's target with `async_extract_config_entry_ids`.
- `config_flow.py` — host + password form, plus an `integration_discovery` step that only asks for the password. Validation borrows the shared listener rather than binding its own socket. The entry `unique_id` is the charger serial, so re-running the flow repairs a changed IP.

## Behavior constraints

- `start_charging` service: reservations max 24h in the future; `max_amps` above the user-configured max is clamped to it, above the device hardware max raises an error.
- The library auto-stops an active reservation/completed state before starting a new charge; the integration does not need to handle that.
- Max amps: on a model that applies the amperage only at session start (Telestar EC311S, per the
  library's capability table), the number entity goes **unavailable while charging** and
  `async_set_max_amps` raises `HomeAssistantError` rather than swallowing the refusal. The charger
  echoes a mid-charge change back within seconds and then ignores it, so an enabled control would
  display a limit that is not the one being delivered.
