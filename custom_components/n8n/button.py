"""Button platform: trigger n8n workflows."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import N8nApiError
from .const import (
    ATTR_TAGS,
    ATTR_TRIGGER_MODE,
    ATTR_WEBHOOK_PATH,
    ATTR_WORKFLOW_ID,
    ATTR_WORKFLOW_NAME,
    DOMAIN,
)
from .coordinator import N8nDataUpdateCoordinator
from .entity import N8nEntity
from .models import Workflow

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up n8n trigger buttons."""
    coordinator: N8nDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    known: set[str] = set()

    @callback
    def _async_add_from_coordinator() -> None:
        if not coordinator.data:
            return
        new_entities: list[N8nTriggerButton] = []
        for workflow in coordinator.data.workflows:
            if workflow.workflow_id in known:
                continue
            known.add(workflow.workflow_id)
            new_entities.append(N8nTriggerButton(coordinator, workflow.workflow_id))
        if new_entities:
            async_add_entities(new_entities)

    _async_add_from_coordinator()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_from_coordinator))


class N8nTriggerButton(N8nEntity, ButtonEntity):
    """Button that triggers an n8n workflow once."""

    def __init__(
        self, coordinator: N8nDataUpdateCoordinator, workflow_id: str
    ) -> None:
        super().__init__(coordinator)
        self._workflow_id = workflow_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_run_{workflow_id}"
        workflow = self._workflow
        name = workflow.name if workflow else f"Workflow {workflow_id}"
        self._attr_name = f"Run {name}"

    @property
    def _workflow(self) -> Workflow | None:
        return self.coordinator.get_workflow(self._workflow_id)

    @property
    def available(self) -> bool:
        """Return True when the API is reachable and the workflow is known."""
        return (
            super().available
            and self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._workflow is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return safe trigger metadata."""
        workflow = self._workflow
        if not workflow:
            return {ATTR_WORKFLOW_ID: self._workflow_id}
        return {
            ATTR_WORKFLOW_ID: workflow.workflow_id,
            ATTR_WORKFLOW_NAME: workflow.name,
            ATTR_TAGS: workflow.tags,
            ATTR_WEBHOOK_PATH: workflow.webhook_path,
            ATTR_TRIGGER_MODE: workflow.trigger_mode,
        }

    async def async_press(self) -> None:
        """Trigger the workflow via webhook or API execute."""
        workflow = self._workflow
        try:
            result = await self.coordinator.client.async_trigger_workflow(
                self._workflow_id,
                webhook_path=workflow.webhook_path if workflow else None,
            )
            _LOGGER.debug(
                "Triggered workflow %s via %s",
                self._workflow_id,
                result.get("mode"),
            )
        except N8nApiError as err:
            _LOGGER.error("Failed to trigger workflow %s: %s", self._workflow_id, err)
            raise
        await self.coordinator.async_request_refresh()
