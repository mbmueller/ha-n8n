"""The n8n Home Assistant custom integration."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import N8nApiClient, N8nApiError, N8nAuthError
from .const import (
    ATTR_WORKFLOW_ID,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
    WEBHOOK_HEADER,
)
from .coordinator import N8nDataUpdateCoordinator
from .webhook import async_register_webhook_view, inbound_webhook_path, inbound_webhook_url

_LOGGER = logging.getLogger(__name__)

type N8nConfigEntry = ConfigEntry

SERVICE_TRIGGER = "trigger_workflow"
SERVICE_REFRESH = "refresh"
SERVICE_ACTIVATE = "activate_workflow"
SERVICE_DEACTIVATE = "deactivate_workflow"

CONF_WEBHOOK_NOTIFIED = "webhook_notified"


def trigger_body_from_service_data(service_data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the JSON body from a trigger service call (`data` or `payload`)."""
    body = service_data.get("data")
    if body is None:
        body = service_data.get("payload")
    return body if isinstance(body, dict) else None


async def async_setup_entry(hass: HomeAssistant, entry: N8nConfigEntry) -> bool:
    """Set up n8n from a config entry."""
    await _async_ensure_webhook_secrets(hass, entry)

    client = N8nApiClient.from_hass(
        hass,
        entry.data[CONF_BASE_URL],
        entry.data[CONF_API_KEY],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    coordinator = N8nDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    async_register_webhook_view(hass)
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )
    await _async_register_services(hass)
    _async_maybe_notify_webhook_credentials(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: N8nConfigEntry) -> bool:
    """Unload an n8n config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        remaining = [
            key
            for key in hass.data.get(DOMAIN, {})
            if key not in ("webhook_view_registered", "services_registered")
        ]
        if not remaining:
            hass.services.async_remove(DOMAIN, SERVICE_TRIGGER)
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
            hass.services.async_remove(DOMAIN, SERVICE_ACTIVATE)
            hass.services.async_remove(DOMAIN, SERVICE_DEACTIVATE)
            hass.data.get(DOMAIN, {}).pop("services_registered", None)
    return unload_ok


async def _async_ensure_webhook_secrets(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Backfill inbound webhook id/secret for Phase 0 entries."""
    data = dict(entry.data)
    changed = False
    if not data.get(CONF_WEBHOOK_ID):
        data[CONF_WEBHOOK_ID] = secrets.token_urlsafe(16)
        changed = True
    if not data.get(CONF_WEBHOOK_SECRET):
        data[CONF_WEBHOOK_SECRET] = secrets.token_urlsafe(24)
        changed = True
    if changed:
        hass.config_entries.async_update_entry(entry, data=data)


def _async_maybe_notify_webhook_credentials(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Show inbound webhook URL + secret once (dismissible notification)."""
    if entry.data.get(CONF_WEBHOOK_NOTIFIED):
        return
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    secret = entry.data.get(CONF_WEBHOOK_SECRET)
    if not webhook_id or not secret:
        return
    path = inbound_webhook_path(webhook_id)
    url = inbound_webhook_url(hass, webhook_id)
    from homeassistant.components import persistent_notification

    persistent_notification.async_create(
        hass,
        (
            f"Configure n8n **HTTP Request** → `{url}` "
            f"(path `{path}`).\n\n"
            f"Header `{WEBHOOK_HEADER}` = `{secret}`\n\n"
            "Store the secret in n8n credentials. "
            "This notice is shown once; copy it now."
        ),
        title=f"n8n inbound webhook ({entry.title})",
        notification_id=f"{DOMAIN}_webhook_{entry.entry_id}",
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_WEBHOOK_NOTIFIED: True}
    )


def _resolve_entry_store(
    hass: HomeAssistant, config_entry_id: str | None
) -> dict[str, Any]:
    """Resolve coordinator/client store for a service call."""
    domain_data = hass.data.get(DOMAIN, {})
    entries = {
        key: value
        for key, value in domain_data.items()
        if isinstance(value, dict) and "coordinator" in value
    }
    if config_entry_id:
        store = entries.get(config_entry_id)
        if store is None:
            raise ServiceValidationError(
                f"Unknown n8n config entry: {config_entry_id}"
            )
        return store
    if len(entries) == 1:
        return next(iter(entries.values()))
    if not entries:
        raise ServiceValidationError("n8n is not configured")
    raise ServiceValidationError(
        "Multiple n8n instances configured; pass config_entry_id"
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def async_trigger(call: ServiceCall) -> None:
        store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        client: N8nApiClient = store["client"]
        coordinator: N8nDataUpdateCoordinator = store["coordinator"]
        workflow_id = call.data[ATTR_WORKFLOW_ID]
        try:
            await client.async_trigger_workflow(
                workflow_id,
                webhook_path=call.data.get("webhook_path"),
                data=trigger_body_from_service_data(dict(call.data)),
            )
        except N8nAuthError as err:
            raise HomeAssistantError(str(err)) from err
        except N8nApiError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    async def async_refresh(call: ServiceCall) -> None:
        entry_id = call.data.get("config_entry_id")
        if entry_id:
            store = _resolve_entry_store(hass, entry_id)
            await store["coordinator"].async_request_refresh()
            return
        for key, value in hass.data.get(DOMAIN, {}).items():
            if isinstance(value, dict) and "coordinator" in value:
                await value["coordinator"].async_request_refresh()

    async def async_activate(call: ServiceCall) -> None:
        store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        try:
            await store["client"].async_activate_workflow(call.data[ATTR_WORKFLOW_ID])
        except N8nApiError as err:
            raise HomeAssistantError(str(err)) from err
        await store["coordinator"].async_request_refresh()

    async def async_deactivate(call: ServiceCall) -> None:
        store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        try:
            await store["client"].async_deactivate_workflow(
                call.data[ATTR_WORKFLOW_ID]
            )
        except N8nApiError as err:
            raise HomeAssistantError(str(err)) from err
        await store["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER,
        async_trigger,
        schema=vol.Schema(
            {
                vol.Required(ATTR_WORKFLOW_ID): cv.string,
                vol.Optional("config_entry_id"): cv.string,
                vol.Optional("webhook_path"): cv.string,
                vol.Optional("data"): dict,
                vol.Optional("payload"): dict,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        async_refresh,
        schema=vol.Schema({vol.Optional("config_entry_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE,
        async_activate,
        schema=vol.Schema(
            {
                vol.Required(ATTR_WORKFLOW_ID): cv.string,
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DEACTIVATE,
        async_deactivate,
        schema=vol.Schema(
            {
                vol.Required(ATTR_WORKFLOW_ID): cv.string,
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    domain_data["services_registered"] = True
