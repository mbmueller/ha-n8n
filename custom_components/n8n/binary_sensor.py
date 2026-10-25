"""Binary sensor: n8n Public API connectivity."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import N8nDataUpdateCoordinator
from .entity import N8nEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the API connectivity binary sensor."""
    coordinator: N8nDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([N8nApiBinarySensor(coordinator)])


class N8nApiBinarySensor(N8nEntity, BinarySensorEntity):
    """On when the last coordinator poll reached n8n successfully."""

    _attr_name = "API"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: N8nDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_api_ok"

    @property
    def is_on(self) -> bool:
        """Return True if the n8n API was reachable on the last update."""
        return bool(self.coordinator.last_update_success and self.coordinator.data)
