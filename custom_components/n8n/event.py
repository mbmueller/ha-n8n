"""Event platform: inbound n8n → HA webhook events."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_WEBHOOK_ID, DOMAIN
from .coordinator import N8nDataUpdateCoordinator
from .entity import N8nEntity
from .webhook import SIGNAL_WEBHOOK_EVENT, inbound_webhook_path
from .webhook_secrets import list_webhook_secrets


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the inbound webhook event entity."""
    coordinator: N8nDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([N8nInboundEventEntity(coordinator)])


class N8nInboundEventEntity(N8nEntity, EventEntity):
    """Event entity updated when n8n posts to the inbound webhook."""

    _attr_name = "Inbound webhook"
    _attr_event_types = ["n8n_webhook", "n8n_trigger"]

    def __init__(self, coordinator: N8nDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_inbound"
        webhook_id = coordinator.entry.data.get(CONF_WEBHOOK_ID, "")
        self._webhook_path = (
            inbound_webhook_path(webhook_id) if webhook_id else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the inbound path and secret count (never secret values)."""
        return {
            "webhook_path": self._webhook_path,
            "auth_header": "X-N8N-HA-Secret",
            "secret_count": len(list_webhook_secrets(dict(self._entry.data))),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to inbound webhook dispatcher signals."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_WEBHOOK_EVENT}_{self._entry.entry_id}",
                self._handle_webhook,
            )
        )

    @callback
    def _handle_webhook(self, event_data: dict[str, Any]) -> None:
        """Push a new event onto this entity from the webhook handler."""
        event_type = str(event_data.get("event_type") or "n8n_webhook")
        if event_type not in self._attr_event_types:
            # Dynamically allow custom event_type values from n8n payloads.
            self._attr_event_types = [*self._attr_event_types, event_type]
        self._trigger_event(
            event_type,
            {
                "message": event_data.get("message"),
                "data": event_data.get("data") or {},
                "received_at": event_data.get("received_at"),
                "entry_id": event_data.get("entry_id"),
            },
        )
        self.async_write_ha_state()
