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
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import N8nDataUpdateCoordinator
from .webhook import (
    async_notify_new_inbound_secret,
    async_register_webhook_view,
    reset_webhook_auth_failures,
)
from .webhook_secrets import (
    add_secret,
    list_webhook_secrets,
    migrate_webhook_secrets,
    revoke_secret,
    rotate_secrets,
)

_LOGGER = logging.getLogger(__name__)

type N8nConfigEntry = ConfigEntry

SERVICE_TRIGGER = "trigger_workflow"
SERVICE_REFRESH = "refresh"
SERVICE_ACTIVATE = "activate_workflow"
SERVICE_DEACTIVATE = "deactivate_workflow"
SERVICE_CREATE_INBOUND_SECRET = "create_inbound_secret"
SERVICE_REVOKE_INBOUND_SECRET = "revoke_inbound_secret"
SERVICE_ROTATE_INBOUND_SECRET = "rotate_inbound_secret"

CONF_WEBHOOK_NOTIFIED = "webhook_notified"

_SERVICE_NAMES = (
    SERVICE_TRIGGER,
    SERVICE_REFRESH,
    SERVICE_ACTIVATE,
    SERVICE_DEACTIVATE,
    SERVICE_CREATE_INBOUND_SECRET,
    SERVICE_REVOKE_INBOUND_SECRET,
    SERVICE_ROTATE_INBOUND_SECRET,
)


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
    _async_maybe_notify_initial_secret(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
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
            if key
            not in (
                "webhook_view_registered",
                "services_registered",
                "webhook_auth_failures",
            )
        ]
        if not remaining:
            for name in _SERVICE_NAMES:
                if hass.services.has_service(DOMAIN, name):
                    hass.services.async_remove(DOMAIN, name)
            hass.data.get(DOMAIN, {}).pop("services_registered", None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_ensure_webhook_secrets(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Backfill webhook id and migrate to the multi-secret store."""
    data = dict(entry.data)
    changed = False
    if not data.get(CONF_WEBHOOK_ID):
        data[CONF_WEBHOOK_ID] = secrets.token_urlsafe(16)
        changed = True
    data, migrated = migrate_webhook_secrets(data)
    if migrated:
        changed = True
    if changed:
        hass.config_entries.async_update_entry(entry, data=data)


def _async_maybe_notify_initial_secret(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """One-time notification for the secret created during first setup only."""
    if entry.data.get(CONF_WEBHOOK_NOTIFIED):
        return
    records = list_webhook_secrets(dict(entry.data))
    if not records:
        return
    # Prefer the sole / oldest record from initial install.
    record = records[0]
    if not async_notify_new_inbound_secret(hass, entry, record, rotated=False):
        return
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_WEBHOOK_NOTIFIED: True}
    )


def _resolve_entry_store(
    hass: HomeAssistant, config_entry_id: str | None
) -> tuple[str, dict[str, Any]]:
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
        return config_entry_id, store
    if len(entries) == 1:
        entry_id = next(iter(entries))
        return entry_id, entries[entry_id]
    if not entries:
        raise ServiceValidationError("n8n is not configured")
    raise ServiceValidationError(
        "Multiple n8n instances configured; pass config_entry_id"
    )


def _get_config_entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise ServiceValidationError(f"Unknown n8n config entry: {entry_id}")
    return entry


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def async_trigger(call: ServiceCall) -> None:
        _, store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
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
            _, store = _resolve_entry_store(hass, entry_id)
            await store["coordinator"].async_request_refresh()
            return
        for key, value in hass.data.get(DOMAIN, {}).items():
            if isinstance(value, dict) and "coordinator" in value:
                await value["coordinator"].async_request_refresh()

    async def async_activate(call: ServiceCall) -> None:
        _, store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        try:
            await store["client"].async_activate_workflow(call.data[ATTR_WORKFLOW_ID])
        except N8nApiError as err:
            raise HomeAssistantError(str(err)) from err
        await store["coordinator"].async_request_refresh()

    async def async_deactivate(call: ServiceCall) -> None:
        _, store = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        try:
            await store["client"].async_deactivate_workflow(
                call.data[ATTR_WORKFLOW_ID]
            )
        except N8nApiError as err:
            raise HomeAssistantError(str(err)) from err
        await store["coordinator"].async_request_refresh()

    async def async_create_inbound_secret(call: ServiceCall) -> None:
        entry_id, _ = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        entry = _get_config_entry(hass, entry_id)
        data, record = add_secret(dict(entry.data), call.data.get("label"))
        hass.config_entries.async_update_entry(entry, data=data)
        entry = _get_config_entry(hass, entry_id)
        async_notify_new_inbound_secret(hass, entry, record, rotated=False)

    async def async_revoke_inbound_secret(call: ServiceCall) -> None:
        entry_id, _ = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        entry = _get_config_entry(hass, entry_id)
        data, removed = revoke_secret(dict(entry.data), call.data["secret_id"])
        if not removed:
            raise ServiceValidationError(
                "Could not revoke secret (unknown id or last remaining secret)"
            )
        hass.config_entries.async_update_entry(entry, data=data)

    async def async_rotate_inbound_secret(call: ServiceCall) -> None:
        entry_id, _ = _resolve_entry_store(hass, call.data.get("config_entry_id"))
        entry = _get_config_entry(hass, entry_id)
        revoke_id = call.data.get("revoke_secret_id")
        # Default: revoke all previous secrets unless a specific id is given
        # or revoke_all_others is explicitly false (keep others; just add).
        if "revoke_all_others" in call.data:
            revoke_all = bool(call.data.get("revoke_all_others"))
        else:
            revoke_all = not revoke_id
        data, record = rotate_secrets(
            dict(entry.data),
            label=call.data.get("label"),
            revoke_id=revoke_id,
            revoke_all_others=revoke_all,
        )
        hass.config_entries.async_update_entry(entry, data=data)
        reset_webhook_auth_failures(hass, entry_id)
        entry = _get_config_entry(hass, entry_id)
        async_notify_new_inbound_secret(hass, entry, record, rotated=True)

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_INBOUND_SECRET,
        async_create_inbound_secret,
        schema=vol.Schema(
            {
                vol.Optional("label"): cv.string,
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REVOKE_INBOUND_SECRET,
        async_revoke_inbound_secret,
        schema=vol.Schema(
            {
                vol.Required("secret_id"): cv.string,
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ROTATE_INBOUND_SECRET,
        async_rotate_inbound_secret,
        schema=vol.Schema(
            {
                vol.Optional("label"): cv.string,
                vol.Optional("revoke_secret_id"): cv.string,
                vol.Optional("revoke_all_others"): cv.boolean,
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    domain_data["services_registered"] = True
