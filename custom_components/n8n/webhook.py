"""Inbound HTTP webhook: n8n → Home Assistant."""

from __future__ import annotations

import json
import logging
import secrets
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_WEBHOOK_RECEIVED,
    MAX_WEBHOOK_PAYLOAD_BYTES,
    WEBHOOK_HEADER,
)

_LOGGER = logging.getLogger(__name__)

SIGNAL_WEBHOOK_EVENT = f"{DOMAIN}_webhook_event"


def inbound_webhook_path(webhook_id: str) -> str:
    """Return the HA path for the inbound n8n webhook."""
    return f"/api/n8n/webhook/{webhook_id}"


def inbound_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Return an absolute URL hint for docs (uses HA internal URL when set)."""
    path = inbound_webhook_path(webhook_id)
    base = getattr(hass.config, "internal_url", None) or getattr(
        hass.config, "external_url", None
    )
    if base:
        return f"{str(base).rstrip('/')}{path}"
    return path


class N8nWebhookView(HomeAssistantView):
    """Accept POSTs from n8n with a shared-secret header."""

    name = "api:n8n:webhook"
    url = "/api/n8n/webhook/{webhook_id}"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request, webhook_id: str) -> web.Response:
        """Handle an inbound webhook from n8n."""
        entry = _find_entry_by_webhook_id(self.hass, webhook_id)
        if entry is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        expected = entry.data.get(CONF_WEBHOOK_SECRET, "")
        provided = request.headers.get(WEBHOOK_HEADER, "")
        if not expected or not secrets.compare_digest(
            str(provided), str(expected)
        ):
            _LOGGER.warning(
                "Rejected n8n webhook for entry %s (invalid secret)",
                entry.entry_id,
            )
            return web.Response(status=HTTPStatus.UNAUTHORIZED)

        try:
            raw = await request.read()
        except Exception:  # noqa: BLE001
            return web.Response(status=HTTPStatus.BAD_REQUEST)

        if len(raw) > MAX_WEBHOOK_PAYLOAD_BYTES:
            return web.Response(status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

        payload: Any = None
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = raw.decode("utf-8", errors="replace")

        event_type = "n8n_webhook"
        message = None
        data: dict[str, Any] = {}
        if isinstance(payload, dict):
            event_type = str(payload.get("event_type") or event_type)
            message = payload.get("message")
            data = {
                k: v
                for k, v in payload.items()
                if k not in ("event_type", "message")
            }
        elif payload is not None:
            data = {"payload": payload}

        event_data = {
            "entry_id": entry.entry_id,
            "webhook_id": webhook_id,
            "event_type": event_type,
            "message": message,
            "data": data,
            "received_at": dt_util.utcnow().isoformat(),
        }

        self.hass.bus.async_fire(EVENT_WEBHOOK_RECEIVED, event_data)
        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_WEBHOOK_EVENT}_{entry.entry_id}",
            event_data,
        )
        _LOGGER.debug(
            "n8n inbound webhook accepted for entry %s (%s)",
            entry.entry_id,
            event_type,
        )
        return web.json_response({"ok": True})


def _find_entry_by_webhook_id(
    hass: HomeAssistant, webhook_id: str
) -> ConfigEntry | None:
    """Locate the config entry that owns this webhook id."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_WEBHOOK_ID) == webhook_id:
            return entry
    return None


def async_register_webhook_view(hass: HomeAssistant) -> None:
    """Register the inbound webhook view once per Home Assistant instance."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("webhook_view_registered"):
        return
    hass.http.register_view(N8nWebhookView(hass))
    domain_data["webhook_view_registered"] = True
