"""Diagnostics with redacted secrets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_WEBHOOK_SECRET, DOMAIN
from .webhook import inbound_webhook_path

TO_REDACT = {
    CONF_API_KEY,
    CONF_WEBHOOK_SECRET,
    "api_key",
    "webhook_secret",
    "X-N8N-API-KEY",
    "X-N8N-HA-Secret",
    "authorization",
    "Authorization",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (secrets redacted)."""
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = stored.get("coordinator")

    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "inbound_webhook_path": inbound_webhook_path(
            entry.data.get("webhook_id", "")
        )
        if entry.data.get("webhook_id")
        else None,
    }

    if coordinator is not None:
        data["coordinator"] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "data": coordinator.data.as_dict() if coordinator.data else None,
        }

    return async_redact_data(data, TO_REDACT)
