# EVSEMaster Home Assistant Integration

This Home Assistant integration provides comprehensive control and monitoring of EVSE chargers that are compatible with the EVSEMaster app. While all testing was done on Telestar device, it should work with all devices that use the app like the one from Besen, Telestar, evseODM, Morec, Deltacom, etc.

The underlying implementation is factored out to a separate Python package: https://github.com/RafaelSchridi/evsemaster

## Verified Compatible Devices
- Telestar EC311S6
- [Besen B20](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/1)
- [Morec MC20CAPP / MC20AAPP](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/6)

## Credits

This Home Assistant integration is based on the excellent work by **[@johnwoo-nl](https://github.com/johnwoo-nl)** in the **[emproto](https://github.com/johnwoo-nl/emproto)** Node.js library that reverse-engineered the EVSEMaster protocol. All the hard work of understanding the protocol, packet structures, and communication patterns was done by @johnwoo-nl.


# Features
- Various sensors for monitoring charger status, energy consumption, and more (see specifics below).
- Start/stop charging control.
- Custom Action to start a single charging session with start delay and optional stop time.

# Limitations
- Currently supports only a single charger per Home Assistant instance.

---

## Services/Actions

### Start Charging (`evsemaster.start_charging`)

Start a charging session with optional parameters for delayed start and maximum duration.

**Parameters:**
- **`max_amps`** (optional): Maximum charging amperage in Amperes (A). If not specified, the charger's configured max amps will be used. Values above the **configured** max are clamped to it; values above the device **hardware** limit raise an error.
- **`start_datetime`** (optional): When to start charging. Format: ISO 8601 datetime string. If not specified, charging starts immediately. Needs to be within **24 hours** from now. If timezone is not specified, the local timezone will be assumed.
- **`duration_hours`** (optional): Maximum charging duration in hours. Range: 1-24 hours. If not specified, charging will continue until manually stopped or the vehicle is fully charged.
- **`target.device_id`**: The device ID of the charger to control. Currently, only a single charger is supported per Home Assistant instance. so nothing is done with this **yet**.

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

---

## Entities

### Sensors

#### **Current State** (`sensor.*_current_state`)
Shows the current operational state of the charger.  
I.e., whether it is idle, charging, waiting, or not connected.

#### **Current Power** (`sensor.*_current_power`)
Real-time charging power consumption in Watts (W) while charging.  
**Should** be over all 3 phases, but not tested.

#### **Plug State** (`sensor.*_plug_state`)
Indicates whether a connector is plugged into the vehicle. 
I.e., whether the vehicle is connected to the charger or not and if its locked.

#### **Inner Temperature** (`sensor.*_inner_temperature`)
Internal charger temperature in Celsius (°C).

#### **Outer Temperature** (`sensor.*_outer_temperature`)
Ambient/external temperature reading in Celsius (°C).
- **Note:** On some devices like the Telestar and Besen this sensor is just the inner temperature again.

#### **Total kWh** (`sensor.*_total_kwh`)
Total cumulative energy delivered by the charger since it was first installed. This is a persistent counter that only increases.

#### **Session kWh** (`sensor.*_charge_kwh`)
Total cumulative energy delivered by the charger in the current charging session. This counter resets back to `0` when the next charging session starts.

#### **Session Duration** (`sensor.*_charge_duration`)
Duration of the current charging session in seconds. This counter resets back to `0` when the next charging session starts.

#### **Session Time** (`sensor.*_session_start_datetime`)
Date/time when the current or last charging session started.

#### **Reservation Start** (`sensor.*_reservation_datetime`)
The scheduled start time for a charging session if one is set via the `start_charging` service.

#### **Reservation Duration** (`sensor.*_reservation_max_duration`)
The duration for a reserved charging session in minutes. set via the `start_charging` service.


### Binary Sensors

#### **Plugged In** (`binary_sensor.*_plug_state`)
Indicates whether a connector is currently plugged into a vehicle.

#### **Charging** (`binary_sensor.*_charging_state`)
Indicates whether the charger is actively charging.

---

### Buttons

#### **Start Charging** (`button.*_start_charging`)
Triggers a charging session immediately or with optional start delay and duration.
- **Availability:** Only available when a vehicle is connected

#### **Stop Charging** (`button.*_stop_charging`)
Stops the current charging session.
- **Availability:** Only available when a vehicle is connected


## Configuration Entities
These appear in the **Configuration** section of the device page.

#### **Max Amps** (`number.*_max_amps`)
Sets the maximum charging current for the charger. Range: 6 A to the device hardware limit.
- **Warning:** Some devices (e.g. Besen B20) support changing this value during an active charging session, while others do not (e.g. Telestar EC311S6) and will return an error. If your device does not support dynamic current adjustment, only change this value when the charger is idle.

#### **Nickname** (`text.*_nickname`)
Custom name for the charger device for easy identification. Also changes the name displayed on the charger itself.
- **Max Length:** Device-dependent (typically 28-32 characters)


## Diagnostic Entities

These entities are disabled by default and appear in the **Diagnostic** section of the device page.

##### **Device Clock Offset** (`sensor.*_time_delta`)
Clock skew between the charger's internal clock and local time in seconds. Some firmware versions have a bug where the device clock drifts by weeks; when a discrepancy of more than 24 hours is detected, this integration automatically compensates when scheduling sessions. `0` means no workaround is active.

##### **L1/L2/L3 Voltage** (`sensor.*_l1_voltage`, `l2_voltage`, `l3_voltage`)
Per-phase voltage in Volts (V).

##### **L1/L2/L3 Current** (`sensor.*_l1_current`, `l2_current`, `l3_current`)
Per-phase current in Amperes (A).
