"""Config flow for the n8n integration."""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import N8nApiClient, N8nApiError, N8nAuthError
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
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

                    return self.async_create_entry(
                        title=urlparse(base_url).netloc or "n8n",
                        data={
                            CONF_BASE_URL: base_url,
                            CONF_API_KEY: user_input[CONF_API_KEY],
                            CONF_VERIFY_SSL: verify_ssl,
                            CONF_URL: base_url,
                            CONF_WEBHOOK_ID: secrets.token_urlsafe(16),
                            CONF_WEBHOOK_SECRET: secrets.token_urlsafe(24),
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
