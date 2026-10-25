"""DataUpdateCoordinator for n8n workflows."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import N8nApiClient, N8nApiError, N8nAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import CoordinatorData

_LOGGER = logging.getLogger(__name__)


class N8nDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Poll n8n for workflow metadata and API reachability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: N8nApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )
        self.entry = entry
        self.client = client

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch workflows from n8n."""
        try:
            workflows = await self.client.async_get_workflows()
        except N8nAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except N8nApiError as err:
            raise UpdateFailed(str(err)) from err

        return CoordinatorData(workflows=workflows, reachable=True)

    def get_workflow(self, workflow_id: str) -> Any:
        """Return a cached workflow by id, or None."""
        if not self.data:
            return None
        return self.data.workflow_by_id(workflow_id)
