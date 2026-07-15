# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

HACS custom integration (domain `evsemaster`, `iot_class: local_push`) for EVSE chargers that use the EVSEMaster app. Integration files live at the repo root (`content_in_root: true` in `hacs.json`). All protocol work is delegated to the `evsemaster` Python package, developed in the sibling repo `RafaelSchridi/evsemaster`.

There is no build/lint/test tooling in this repo; to run it, place the repo in a Home Assistant instance as `custom_components/evsemaster/`.

## Library loading and dev workflow

`evse_loader.py` imports from a local `./evsemaster` package directory first (development), falling back to the installed PyPI package (release). To test unreleased library changes inside HA, copy or symlink `../evsemaster/evsemaster/` into this repo. All modules must import protocol classes via `from .evse_loader import evse_protocol, data_types` — never import `evsemaster` directly, or the local-first fallback breaks.

Releases pin the library version in `manifest.json` requirements (`evsemaster==x.y.z`); bump it together with the manifest `version` field.

## Architecture

- `coordinator.py` — `EVSEMasterDataUpdateCoordinator` is the hub. It owns the `SimpleEVSEProtocol` instance and combines push with poll:
  - Push (primary data path, hence `local_push`): protocol `event_callback` → `_on_protocol_event` → `async_set_updated_data`.
  - Poll (60s): only ensures connect/login and re-requests status; a secondary 30-minute timer refreshes device essentials (nickname, configured amps).
  - `coordinator.data` is a `DataSchema` pydantic model: `status` (`EvseStatus`), `charging_status` (`ChargingStatus`), `device` (`DeviceSchema`, which extends the library's `EvseDeviceInfo` with HA `device_info`).
  - All control actions (start/stop charging, nickname, max amps) go through `async_*` wrappers on the coordinator that validate and translate errors to `HomeAssistantError`.
- Platforms (`sensor`, `binary_sensor`, `button`, `text`, `number`): flat entity classes sharing a `_Base(CoordinatorEntity)`; state is read from `self.entry` (= `coordinator.data`). Unique IDs are `{serial_number}_{key}`; display names come from `translations/en.json` via `_attr_translation_key`.
- `__init__.py` registers the `evsemaster.start_charging` service (fields in `services.yaml`, keys in `const.py`).
- `config_flow.py` — single-step host + password form, validated by performing a real login.
- Only one charger per HA instance is supported; the service handler ignores `device_id` for now.

## Behavior constraints

- `start_charging` service: reservations max 24h in the future; `max_amps` above the user-configured max is clamped to it, above the device hardware max raises an error.
- The library auto-stops an active reservation/completed state before starting a new charge; the integration does not need to handle that.
- Some devices reject changing max amps during an active charge session (device-dependent, see README).
