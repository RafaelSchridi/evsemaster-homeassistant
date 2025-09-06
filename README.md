# EVSEMaster Home Assistant Integration

This Home Assistant integration provides comprehensive control and monitoring of EVSE chargers that are compatible with the EVSEMaster app. While all testing was done on Telestar device, it should work with all devices that use the app like the one from Besen, Telestar, evseODM, Morec, Deltacom, etc.

## Verified Compatible Devices
- Telestar EC311S6

## Credits

This Home Assistant integration is based on the excellent work by **[@johnwoo-nl](https://github.com/johnwoo-nl)** in the **[emproto](https://github.com/johnwoo-nl/emproto)** Node.js library that reverse-engineered the EVSEMaster protocol. All the hard work of understanding the protocol, packet structures, and communication patterns was done by @johnwoo-nl.

This integration translates that knowledge into a pure Python implementation for Home Assistant, but the foundation and protocol understanding comes entirely from @johnwoo-nl's original work.

# Features
- Various sensors for monitoring charger status, energy consumption, and more.
- Start/stop charging control.
- Custom Action to start a single charging session with start delay and optional stop time.

# Limitations
- Currently supports only a single charger per Home Assistant instance.