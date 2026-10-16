"""Shared entity base for all EVSEMaster platforms."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DataSchema, EVSEMasterDataUpdateCoordinator


class EVSEMasterEntity(CoordinatorEntity[EVSEMasterDataUpdateCoordinator]):
    """Ties an entity to one charger.

    Identity comes from the config entry unique id (the charger serial), which is fixed before
    entities are created, so two chargers can never collide on a unique id.
    """

    _attr_has_entity_name = True
    _unique_id_key: str

    def __init__(self, coordinator: EVSEMasterDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_{self._unique_id_key}"
        self._attr_device_info = coordinator.device_info

    @property
    def entry(self) -> DataSchema:
        return self.coordinator.data


class EVSEMasterLiveEntity(EVSEMasterEntity):
    """Reports what the charger pushes, so it is only current while the charger is still reporting."""

    @property
    def available(self) -> bool:
        device = self.coordinator.device
        return super().available and device is not None and device.is_receiving
