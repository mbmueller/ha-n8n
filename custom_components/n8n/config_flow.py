"""Config flow for the n8n integration (stub — no live API yet)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers import config_validation as cv

from .const import CONF_API_KEY, CONF_BASE_URL, CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)


def _normalize_base_url(url: str) -> str:
    """Normalize scheme+host+port for unique_id (no trailing slash)."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("invalid_url")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class N8nConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for n8n.

    Phase 0: accepts URL + API key + verify_ssl, stores the entry, and does
    **not** call the live n8n API yet (validation lands in Phase 1).
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                base_url = _normalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                await self.async_set_unique_id(base_url.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=urlparse(base_url).netloc or "n8n",
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_VERIFY_SSL: user_input.get(
                            CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL
                        ),
                        # Keep CONF_URL alias-friendly for future HA helpers
                        CONF_URL: base_url,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
