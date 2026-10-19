# EVSEMaster Home Assistant Integration

This Unofficial Home Assistant integration provides comprehensive control and monitoring of EVSE chargers that are compatible with the EVSEMaster app. While all testing was done on Telestar device, it should work with all devices that use the app like the one from Besen, Telestar, evseODM, Morec, Deltacom, etc.

The underlying implementation is factored out to a separate Python package: https://github.com/RafaelSchridi/evsemaster

## Verified Compatible Devices
- Telestar EC311S & EC311S6
- [Besen B20](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/1)
- [Morec MC20CAPP / MC20AAPP](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/9)

Charger working and not on this list? [Report it here to help others!](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/new?template=working-device.yml)

## LAN Only
If you only need basic control and are within bluetooth range, consider using the [bluetooth integration in home assistant](https://www.home-assistant.io/integrations/besen). This integration is for LAN control only.

## Installation
If you do not have HACS yet, [follow the official guide](https://hacs.xyz/docs/use/download/download/).

### 1. Install with HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=RafaelSchridi&repository=evsemaster-homeassistant&category=integration)

1. Click the above link to open the repository in HACS.
2. Click Download
3. Restart Home Assistant

<details>
<summary>Or add it manually</summary>

1. Go to **HACS** in the Home Assistant sidebar.
2. Click the **⋮** menu (top right) → **Custom repositories**.
3. Repository: `https://github.com/RafaelSchridi/evsemaster-homeassistant`
4. Type: **Integration**, then click **Add**.
5. Search for **EVSEMaster** in HACS, open it and click **Download**.
6. Restart Home Assistant.

</details>

### 2. Add the integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=evsemaster)

Or: **Settings** → **Devices & Services** → **Add Integration** → search for **EVSEMaster**.

## Credits

This Home Assistant integration is based on the excellent work by **[@johnwoo-nl](https://github.com/johnwoo-nl)** in the **[emproto](https://github.com/johnwoo-nl/emproto)** Node.js library that reverse-engineered the EVSEMaster protocol. All the hard work of understanding the protocol, packet structures, and communication patterns was done by @johnwoo-nl.


# Features
- Various sensors for monitoring charger status, energy consumption, and more (see specifics below).
- Start/stop charging control.
- Custom Action to start a single charging session with start delay and optional stop time.
- Actions to set the charger's own weekly plan and to read the sessions stored on the charger.
- Multiple chargers per Home Assistant instance, each its own device.
- Chargers announce themselves, so extra ones are discovered automatically (see below).

# Limitations

- Doesn't do setup: use the EVSEMaster app at least once to connect the charger to Wi-Fi.
- Discovery only finds *additional* chargers: Home Assistant does not load this integration until one charger is set up, so the first one is always added by hand.
- The integration acknowledges each finished session's record, which stops the charger from rebroadcasting it. The
  EVSEMaster app builds its charge history only from records it acknowledged itself, so sessions Home Assistant saw
  first are missing from the app's history. The charger keeps its last 300 sessions either way: read them with
  `evsemaster.get_charge_history`.
- Your Home Assistant must be able to receive the chargers' broadcast packets on UDP port 28376.
  A separate VLAN, or Docker bridge networking without `network_mode: host`, blocks them; without those broadcasts discovery and automatic re-login do not work.

---

## Services/Actions

### Start Charging (`evsemaster.start_charging`)

Start a charging session with optional parameters for delayed start and maximum duration.

**Parameters:**
- **`max_amps`** (optional): Maximum charging amperage in Amperes (A). If not specified, the charger's configured max amps will be used. Values above the **configured** max are clamped to it; values above the device **hardware** limit raise an error.
- **`start_datetime`** (optional): When to start charging. Format: ISO 8601 datetime string. If not specified, charging starts immediately. Needs to be within **24 hours** from now. If timezone is not specified, the local timezone will be assumed.
- **`duration_hours`** (optional): Maximum charging duration in hours. Range: 1-24 hours. If not specified, charging will continue until manually stopped or the vehicle is fully charged.
- **`target`**: The charger(s) to control. Targeting a device, entity, area and labels all work; the action runs on every EVSEMaster charger the target resolves to. If some of them fail, the others still get the command, and the error names each charger that failed.

**Example:**
```yaml
service: evsemaster.start_charging
target:
  device_id: YOUR_DEVICE_ID
data:
  max_amps: 16
  start_datetime: "2024-01-25T14:30:00+01:00"
  duration_hours: 2
```

### Set Weekly Plan (`evsemaster.set_weekly_plan`)

Replace the charger's own weekly schedule, like the EVSEMaster app does: one charging window on the chosen days. A car
plugged in during the window charges until the window ends; a car already plugged in starts when it opens. The charger
runs the plan by itself, without Home Assistant.

**Parameters:**
- **`days`** (optional): `monday` … `sunday`. Days left out are switched off; no days at all turns the plan off.
- **`start_time`**: When the window opens.
- **`end_time`**: When it closes. An end before the start runs into the next day; an end equal to the start is 24 hours.

A window that opens cancels a reservation made with `start_charging`.

```yaml
service: evsemaster.set_weekly_plan
target:
  device_id: YOUR_DEVICE_ID
data:
  days: [monday, tuesday, wednesday, thursday, friday]
  start_time: "22:00"
  end_time: "06:00"
```

### Get Charge History (`evsemaster.get_charge_history`)

Returns the sessions stored on the charger (up to 300), newest first, keyed by charger serial. Each has its start and
stop time, energy, duration, who started and stopped it, and why it stopped. Reading takes about 90 seconds, because
the charger answers one session at a time.

**Parameters:**
- **`limit`** (optional): Return only this many of the newest sessions.

```yaml
service: evsemaster.get_charge_history
target:
  device_id: YOUR_DEVICE_ID
data:
  limit: 10
response_variable: history
```

---

## Entities

### Sensors

Live readings go unavailable when the charger sends no heading for 35 seconds. Total Energy, Weekly Plan and the Last Session sensors keep their value.

#### **Current State** (`sensor.*_current_state`)
Shows the current operational state of the charger.  
I.e., whether it is idle, charging, waiting, or not connected.

#### **Current Power** (`sensor.*_current_power`)
Real-time charging power in Watts (W). 
**Should** be over all 3 phases, but not tested.

#### **Plug State** (`sensor.*_plug_state`)
Whether a vehicle is connected, and whether the connector is locked.

#### **Inner Temperature** (`sensor.*_inner_temperature`)
Internal charger temperature in Celsius (°C).

#### **Outer Temperature** (`sensor.*_outer_temperature`)
Ambient/external temperature in Celsius (°C). 
- **Note:** On some devices this sensor is just the inner temperature again.

#### **Total Energy** (`sensor.*_total_energy`)
Total cumulative energy delivered by the charger since it was first installed. This is a persistent counter that only increases.

#### **Session Energy** (`sensor.*_session_energy`)
Total cumulative energy delivered by the charger in the current charging session. This counter resets back to `0` when the next charging session starts.

#### **Session Duration** (`sensor.*_session_duration`)
Duration of the current charging session in seconds. This counter resets back to `0` when the next charging session starts.

#### **Session Start** (`sensor.*_session_start`)
Date/time when the current or last charging session started.

#### **Session Max Current** (`sensor.*_session_max_current`)
The current limit the charger confirmed for the current or last session, in Amperes (A). Use it to check that
a `max_amps` passed to `start_charging` was applied.

#### **Reservation Start** (`sensor.*_reservation_start`)
When a reserved session starts, set with `start_charging`

#### **Reservation Duration** (`sensor.*_reservation_duration`)
The time limit of a reserved session in minutes.

#### **Fault** (`sensor.*_fault`)
The fault the charger reports, such as an emergency stop, over temperature or a CP error, or `No fault`. With several
at once the state is the first, and the `faults` attribute lists all of them; the EVSEMaster app shows only the first.

#### **Last Session Stop Reason** (`sensor.*_last_session_stop_reason`)
Why the last session stopped: stopped from the app or Home Assistant, cable unplugged, time limit reached, energy limit
reached, power loss or reservation cancelled. **Disabled by default.**

#### **Last Session End** (`sensor.*_last_session_end`)
When the last session ended. Attributes: start time, who started and stopped it, and the charge id. **Disabled by default.**

#### **Weekly Plan** (`sensor.*_weekly_plan`)
`On` when the charger's weekly plan has any day enabled. Each enabled day is an attribute with its start time and duration. 
Set it with `evsemaster.set_weekly_plan`.


### Binary Sensors

#### **Plug State** (`binary_sensor.*_plug_state`)
Indicates whether a connector is currently plugged into a vehicle.

#### **Charging State** (`binary_sensor.*_charging_state`)
Indicates whether the charger is actively charging.

---

### Buttons

#### **Start Charging** (`button.*_start_charging`)
Starts charging now, at the configured max amps and without a time limit.

#### **Stop Charging** (`button.*_stop_charging`)
Stops the current charging session, or cancels a scheduled one.
With no car connected and nothing scheduled, pressing it reports that there is nothing to stop.

---

## Configuration Entities
These appear in the **Configuration** section of the device page.

#### **Max Amps** (`number.*_max_amps`)
Sets the maximum charging current for the charger. Range: 6 A to the device hardware limit.
- **Warning:** Some devices (e.g. Besen B20) apply a new value during an active charging session; others
  (Telestar EC311S and EC311S6) only apply it when a charge starts, so on those this entity is unavailable while charging.

#### **Display Language** (`select.*_display_language`)
The language of the charger's own display: English, Italian, German, French, Spanish, Hebrew, Polish, Turkish or
Chinese (Traditional).

#### **Nickname** (`text.*_nickname`)
The charger's name, also shown on its own display. Max 28 characters: letters, digits and `_`.


## Diagnostic Entities

These entities are **disabled by default** and appear in the **Diagnostic** section of the device page.

##### **Device Clock Offset** (`sensor.*_device_clock_offset`)
Clock skew between the charger's internal clock and local time in seconds. Some firmware versions have a bug where the device clock drifts by weeks; when a discrepancy of more than 24 hours is detected, this integration automatically compensates when scheduling sessions. `0` means no workaround is active.

##### **Last Seen** (`sensor.*_last_seen`)
When the charger last sent anything other than its periodic announcement. 
**It updates with almost every packet,** so enable it only while troubleshooting.

##### **L1/L2/L3 Voltage** (`sensor.*_l1_voltage`, `l2_voltage`, `l3_voltage`)
Per-phase voltage in Volts (V).

##### **L1/L2/L3 Current** (`sensor.*_l1_current`, `l2_current`, `l3_current`)
Per-phase current in Amperes (A).
