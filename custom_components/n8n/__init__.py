"""The n8n Home Assistant custom integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

type N8nConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: N8nConfigEntry) -> bool:
    """Set up n8n from a config entry.

    Phase 0 stub: stores the entry and forwards platforms when any are listed.
    Live API client / coordinator wiring lands in Phase 1.
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform(p) for p in PLATFORMS]
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: N8nConfigEntry) -> bool:
    """Unload an n8n config entry."""
    unload_ok = True
    if PLATFORMS:
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, [Platform(p) for p in PLATFORMS]
        )

    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok
