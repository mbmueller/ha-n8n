"""Config flow for the n8n integration."""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import N8nApiClient, N8nApiError, N8nAuthError
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_EXECUTION_HISTORY_LIMIT,
    CONF_INBOUND_SECRET_ACTION,
    CONF_INBOUND_SECRET_ID,
    CONF_INBOUND_SECRET_LABEL,
    CONF_SCAN_INTERVAL,
    CONF_TAG_ALLOWLIST,
    CONF_TAG_BLOCKLIST,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRETS,
    CONF_WORKFLOW_ALLOWLIST,
    CONF_WORKFLOW_BLOCKLIST,
    DEFAULT_EXECUTION_HISTORY_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    INBOUND_SECRET_ACTION_CREATE,
    INBOUND_SECRET_ACTION_NONE,
    INBOUND_SECRET_ACTION_REVOKE,
    INBOUND_SECRET_ACTION_ROTATE,
    MAX_EXECUTION_HISTORY_LIMIT,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .webhook_secrets import (
    add_secret,
    list_webhook_secrets,
    new_secret_record,
    revoke_secret,
    rotate_secrets,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): cv.string,
    }
)


def _normalize_base_url(url: str) -> str:
    """Normalize scheme+host+port for unique_id (no trailing slash)."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("invalid_url")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _options_schema(options: dict[str, Any], entry_data: dict[str, Any]) -> vol.Schema:
    """Build the options form schema with current defaults."""
    secret_meta = list_webhook_secrets(entry_data)
    secret_ids = {r["id"]: f"{r['label']} ({r['id']})" for r in secret_meta}
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
            ),
            vol.Optional(
                CONF_WORKFLOW_ALLOWLIST,
                default=options.get(CONF_WORKFLOW_ALLOWLIST, ""),
            ): cv.string,
            vol.Optional(
                CONF_WORKFLOW_BLOCKLIST,
                default=options.get(CONF_WORKFLOW_BLOCKLIST, ""),
            ): cv.string,
            vol.Optional(
                CONF_TAG_ALLOWLIST,
                default=options.get(CONF_TAG_ALLOWLIST, ""),
            ): cv.string,
            vol.Optional(
                CONF_TAG_BLOCKLIST,
                default=options.get(CONF_TAG_BLOCKLIST, ""),
            ): cv.string,
            vol.Optional(
                CONF_EXECUTION_HISTORY_LIMIT,
                default=options.get(
                    CONF_EXECUTION_HISTORY_LIMIT, DEFAULT_EXECUTION_HISTORY_LIMIT
                ),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=1, max=MAX_EXECUTION_HISTORY_LIMIT),
            ),
            vol.Optional(
                CONF_INBOUND_SECRET_ACTION,
                default=INBOUND_SECRET_ACTION_NONE,
            ): vol.In(
                [
                    INBOUND_SECRET_ACTION_NONE,
                    INBOUND_SECRET_ACTION_CREATE,
                    INBOUND_SECRET_ACTION_REVOKE,
                    INBOUND_SECRET_ACTION_ROTATE,
                ]
            ),
            vol.Optional(CONF_INBOUND_SECRET_LABEL, default=""): cv.string,
            vol.Optional(CONF_INBOUND_SECRET_ID, default=""): vol.In(
                [""] + list(secret_ids.keys())
            )
            if secret_ids
            else cv.string,
        }
    )


async def _async_validate_connection(
    hass: HomeAssistant,
    base_url: str,
    api_key: str,
    verify_ssl: bool,
) -> dict[str, str]:
    """Validate the n8n URL and API key. Returns error dict (empty if ok)."""
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = N8nApiClient(session, base_url, api_key, verify_ssl=verify_ssl)
    try:
        await client.async_validate()
    except N8nAuthError:
        return {"base": "invalid_auth"}
    except N8nApiError:
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001 — surface as unknown in the UI
        _LOGGER.exception("Unexpected error validating n8n connection")
        return {"base": "unknown"}
    return {}


class N8nConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for n8n."""

    VERSION = 1

    _reauth_entry_id: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return N8nOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                base_url = _normalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                verify_ssl = user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                errors = await _async_validate_connection(
                    self.hass,
                    base_url,
                    user_input[CONF_API_KEY],
                    verify_ssl,
                )
                if not errors:
                    await self.async_set_unique_id(base_url.lower())
                    self._abort_if_unique_id_configured()

                    initial = new_secret_record("default")
                    return self.async_create_entry(
                        title=urlparse(base_url).netloc or "n8n",
                        data={
                            CONF_BASE_URL: base_url,
                            CONF_API_KEY: user_input[CONF_API_KEY],
                            CONF_VERIFY_SSL: verify_ssl,
                            CONF_URL: base_url,
                            CONF_WEBHOOK_ID: secrets.token_urlsafe(16),
                            CONF_WEBHOOK_SECRETS: [initial],
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication when the API key is rejected."""
        self._reauth_entry_id = self.context.get("entry_id")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a new API key during reauth."""
        errors: dict[str, str] = {}
        entry = None
        if self._reauth_entry_id:
            entry = self.hass.config_entries.async_get_entry(self._reauth_entry_id)

        if user_input is not None and entry is not None:
            base_url = entry.data[CONF_BASE_URL]
            verify_ssl = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            errors = await _async_validate_connection(
                self.hass,
                base_url,
                user_input[CONF_API_KEY],
                verify_ssl,
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]},
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )


class N8nOptionsFlowHandler(OptionsFlow):
    """Handle n8n options (poll interval, filters, inbound secrets)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get(
                CONF_INBOUND_SECRET_ACTION, INBOUND_SECRET_ACTION_NONE
            )
            label = str(user_input.get(CONF_INBOUND_SECRET_LABEL, "") or "").strip()
            secret_id = str(user_input.get(CONF_INBOUND_SECRET_ID, "") or "").strip()

            options = {
                CONF_SCAN_INTERVAL: int(
                    user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ),
                CONF_WORKFLOW_ALLOWLIST: str(
                    user_input.get(CONF_WORKFLOW_ALLOWLIST, "") or ""
                ).strip(),
                CONF_WORKFLOW_BLOCKLIST: str(
                    user_input.get(CONF_WORKFLOW_BLOCKLIST, "") or ""
                ).strip(),
                CONF_TAG_ALLOWLIST: str(
                    user_input.get(CONF_TAG_ALLOWLIST, "") or ""
                ).strip(),
                CONF_TAG_BLOCKLIST: str(
                    user_input.get(CONF_TAG_BLOCKLIST, "") or ""
                ).strip(),
                CONF_EXECUTION_HISTORY_LIMIT: int(
                    user_input.get(
                        CONF_EXECUTION_HISTORY_LIMIT, DEFAULT_EXECUTION_HISTORY_LIMIT
                    )
                ),
            }

            from .webhook import (
                async_notify_new_inbound_secret,
                reset_webhook_auth_failures,
            )

            entry = self.config_entry
            data = dict(entry.data)

            if action == INBOUND_SECRET_ACTION_CREATE:
                data, record = add_secret(data, label or "n8n")
                self.hass.config_entries.async_update_entry(entry, data=data)
                entry = self.hass.config_entries.async_get_entry(entry.entry_id) or entry
                async_notify_new_inbound_secret(self.hass, entry, record, rotated=False)
                _LOGGER.info(
                    "Created inbound webhook secret %s for entry %s",
                    record["id"],
                    entry.entry_id,
                )
            elif action == INBOUND_SECRET_ACTION_REVOKE:
                if not secret_id:
                    errors["base"] = "secret_id_required"
                else:
                    data, removed = revoke_secret(data, secret_id)
                    if not removed:
                        errors["base"] = "secret_revoke_failed"
                    else:
                        self.hass.config_entries.async_update_entry(entry, data=data)
                        _LOGGER.info(
                            "Revoked inbound webhook secret %s for entry %s",
                            secret_id,
                            entry.entry_id,
                        )
            elif action == INBOUND_SECRET_ACTION_ROTATE:
                data, record = rotate_secrets(
                    data,
                    label=label or "rotated",
                    revoke_id=secret_id or None,
                    revoke_all_others=not secret_id,
                )
                self.hass.config_entries.async_update_entry(entry, data=data)
                reset_webhook_auth_failures(self.hass, entry.entry_id)
                entry = self.hass.config_entries.async_get_entry(entry.entry_id) or entry
                async_notify_new_inbound_secret(self.hass, entry, record, rotated=True)
                _LOGGER.info(
                    "Rotated inbound webhook secret for entry %s (new %s)",
                    entry.entry_id,
                    record["id"],
                )

            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(
                        options, dict(self.config_entry.data)
                    ),
                    errors=errors,
                )

            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                dict(self.config_entry.options), dict(self.config_entry.data)
            ),
        )
