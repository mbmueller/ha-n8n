"""Inbound HTTP webhook: n8n → Home Assistant."""

from __future__ import annotations

import json
import logging
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
    DOMAIN,
    EVENT_WEBHOOK_RECEIVED,
    MAX_WEBHOOK_PAYLOAD_BYTES,
    WEBHOOK_AUTH_FAILURE_THRESHOLD,
    WEBHOOK_HEADER,
)
from .webhook_secrets import (
    list_webhook_secrets,
    secret_matches,
    secrets_public_metadata,
)

_LOGGER = logging.getLogger(__name__)

SIGNAL_WEBHOOK_EVENT = f"{DOMAIN}_webhook_event"

_AUTH_FAILURES_KEY = "webhook_auth_failures"


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


def reset_webhook_auth_failures(hass: HomeAssistant, entry_id: str) -> None:
    """Clear auth-failure counters after a successful request or rotation."""
    failures = hass.data.get(DOMAIN, {}).get(_AUTH_FAILURES_KEY)
    if isinstance(failures, dict):
        failures.pop(entry_id, None)


def async_notify_new_inbound_secret(
    hass: HomeAssistant,
    entry: ConfigEntry,
    record: dict[str, str],
    *,
    rotated: bool = False,
) -> bool:
    """Show a newly created secret once in a dismissible persistent notification.

    Existing secrets are never re-displayed — create or rotate to get a value.
    """
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    secret = record.get("secret")
    if not webhook_id or not secret:
        return False

    path = inbound_webhook_path(str(webhook_id))
    url = inbound_webhook_url(hass, str(webhook_id))
    from homeassistant.components import persistent_notification

    action = "Rotated" if rotated else "Created"
    persistent_notification.async_create(
        hass,
        (
            f"{action} inbound webhook secret **{record.get('label', 'default')}** "
            f"(`{record.get('id')}`).\n\n"
            f"Same URL for all secrets: `{url}` (path `{path}`).\n\n"
            f"Header `{WEBHOOK_HEADER}` = `{secret}`\n\n"
            "Copy this into n8n credentials now — **this value is shown only once**. "
            "Existing secrets are not re-displayed; create or rotate to mint a new one. "
            "Secrets never appear on entity attributes or diagnostics."
        ),
        title=f"n8n inbound webhook ({entry.title})",
        notification_id=f"{DOMAIN}_webhook_{entry.entry_id}_{record.get('id', 'new')}",
    )
    return True


def _record_auth_failure(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Count invalid-secret attempts and raise a repair issue when persistent."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    failures: dict[str, int] = domain_data.setdefault(_AUTH_FAILURES_KEY, {})
    count = failures.get(entry.entry_id, 0) + 1
    failures[entry.entry_id] = count
    _LOGGER.warning(
        "Rejected n8n webhook for entry %s (invalid secret, failure %s)",
        entry.entry_id,
        count,
    )
    if count < WEBHOOK_AUTH_FAILURE_THRESHOLD:
        return
    from .repairs import async_create_stale_webhook_issue

    async_create_stale_webhook_issue(hass, entry)


class N8nWebhookView(HomeAssistantView):
    """Accept POSTs from n8n with a shared-secret header (any active secret)."""

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

        provided = request.headers.get(WEBHOOK_HEADER, "")
        if not secret_matches(str(provided), dict(entry.data)):
            _record_auth_failure(self.hass, entry)
            return web.Response(status=HTTPStatus.UNAUTHORIZED)

        reset_webhook_auth_failures(self.hass, entry.entry_id)

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
            "secret_count": len(list_webhook_secrets(dict(entry.data))),
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


# Re-export for diagnostics / event entity convenience.
__all__ = [
    "N8nWebhookView",
    "SIGNAL_WEBHOOK_EVENT",
    "async_notify_new_inbound_secret",
    "async_register_webhook_view",
    "inbound_webhook_path",
    "inbound_webhook_url",
    "reset_webhook_auth_failures",
    "secrets_public_metadata",
]
