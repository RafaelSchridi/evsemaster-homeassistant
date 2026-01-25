# EVSEMaster Home Assistant Integration

This Home Assistant integration provides comprehensive control and monitoring of EVSE chargers that are compatible with the EVSEMaster app. While all testing was done on Telestar device, it should work with all devices that use the app like the one from Besen, Telestar, evseODM, Morec, Deltacom, etc.

## Verified Compatible Devices
- Telestar EC311S6
- [Besen B20](https://github.com/RafaelSchridi/evsemaster-homeassistant/issues/1)

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
- **`max_amps`** (optional): Maximum charging amperage in Amperes (A). Range: 6-32 A. If not specified, the charger's current configured max amps will be used.
- **`start_datetime`** (optional): When to start charging. Format: ISO 8601 datetime string. If not specified, charging starts immediately.
- **`duration_hours`** (optional): Maximum charging duration in hours. Range: 1-24 hours. If not specified, charging will continue until manually stopped or the vehicle is fully charged.
- **`target.device_id`**: The device ID of the charger to control. Currently, only a single charger is supported per Home Assistant instance. so nothing is done with this **yet**.

**Example:**
```yaml
service: evsemaster.start_charging
target:
  device_id: YOUR_DEVICE_ID
data:
  max_amps: 16
  start_datetime: "2024-01-25T14:30:00"
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
- **Note:** On some devices like the Telestar this sensor is just the inner temperature again.

#### **Total Energy** (`sensor.*_total_kwh`)
Total cumulative energy delivered by the charger since it was first installed. This is a persistent counter that only increases.

#### **Reservation Start Time** (`sensor.*_reservation_datetime`)
The scheduled start time for a charging session if one is set via the `start_charging` service.

#### **Reservation Max Duration** (`sensor.*_reservation_max_duration`)
The maximum duration for a reserved charging session in minutes. set via the `start_charging` service.

---

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

### Number Inputs

#### **Max Amps** (`number.*_max_amps`)
Sets the maximum charging current allowed for the charger.
- **Range:** 6-32 A (based on device capability)
- **Effect:** Changes the charging current limit on the charger. This affects all future charging sessions until changed again.
- **Note:** Can't be adjusted during an active charging session.

---

### Text Inputs

#### **Nickname** (`text.*_nickname`)
Custom name for the charger device for easy identification. Also changes the name displayed on the charger itself.
- **Max Length:** Device-dependent (typically 28-32 characters)

---

