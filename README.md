# EVSEMaster Home Assistant Integration

This Home Assistant integration provides comprehensive control and monitoring of EVSE (Electric Vehicle Supply Equipment) chargers that are compatible with the EVSEMaster protocol. This includes chargers from brands like Besen, Telestar, evseODM, Morec, Deltaco, and others that use the same protocol.

## Credits

This Home Assistant integration is based on the excellent work by **[@johnwoo-nl](https://github.com/johnwoo-nl)** in the **[emproto](https://github.com/emproto/emproto)** Node.js library that reverse-engineered the EVSEMaster protocol. All the hard work of understanding the protocol, packet structures, and communication patterns was done by @johnwoo-nl.

This integration translates that knowledge into a pure Python implementation for Home Assistant, but the foundation and protocol understanding comes entirely from @johnwoo-nl's original work.
