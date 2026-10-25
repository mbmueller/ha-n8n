"""DataUpdateCoordinator stub for n8n."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class N8nDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that will poll n8n workflow / execution metadata.

    Phase 0 stub — ``_async_update_data`` returns an empty payload.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from n8n (stub)."""
        return {"workflows": [], "reachable": False}
