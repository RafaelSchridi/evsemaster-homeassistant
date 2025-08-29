"""Local-first loader for evsemaster modules."""

try:
    # Try local evsemaster folder first (development)
    from .evsemaster import evse_protocol, data_types
    import logging
    logging.getLogger(__name__).warning("Using local evsemaster package")
except ImportError:
    # Fall back to installed package (release)
    from evsemaster import evse_protocol, data_types

__all__ = ["evse_protocol", "data_types"]