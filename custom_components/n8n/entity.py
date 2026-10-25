"""Shared entity base for n8n platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import N8nDataUpdateCoordinator


class N8nEntity(CoordinatorEntity[N8nDataUpdateCoordinator]):
    """Base entity tied to an n8n config entry / coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: N8nDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = coordinator.entry
        base_url = coordinator.entry.data.get(CONF_BASE_URL, "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title or "n8n",
            manufacturer=MANUFACTURER,
            configuration_url=base_url or None,
        )
