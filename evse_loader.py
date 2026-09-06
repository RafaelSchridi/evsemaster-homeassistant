"""Local-first loader for evsemaster modules."""

import logging

try:
    # Try local evsemaster folder first (development)
    from .evsemaster import data_types, device, listener

    logging.getLogger(__name__).warning("Using local evsemaster package")
except ImportError:
    # Fall back to installed package (release)
    from evsemaster import data_types, device, listener

    logging.getLogger(__name__).debug("Using installed evsemaster package")

__all__ = ["data_types", "device", "listener"]
