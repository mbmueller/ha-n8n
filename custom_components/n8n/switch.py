"""Switch platform: activate / deactivate n8n workflows."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import N8nApiError, N8nAuthError
from .const import ATTR_TAGS, ATTR_WORKFLOW_ID, ATTR_WORKFLOW_NAME, DOMAIN
from .coordinator import N8nDataUpdateCoordinator
from .entity import N8nEntity
from .models import Workflow

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up n8n workflow switches."""
    coordinator: N8nDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    known: set[str] = set()

    @callback
    def _async_add_from_coordinator() -> None:
        if not coordinator.data:
            return
        new_entities: list[N8nWorkflowSwitch] = []
        for workflow in coordinator.data.workflows:
            if workflow.workflow_id in known:
                continue
            known.add(workflow.workflow_id)
            new_entities.append(N8nWorkflowSwitch(coordinator, workflow.workflow_id))
        if new_entities:
            async_add_entities(new_entities)

    _async_add_from_coordinator()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_from_coordinator))


class N8nWorkflowSwitch(N8nEntity, SwitchEntity):
    """Represent whether an n8n workflow is active."""

    def __init__(
        self, coordinator: N8nDataUpdateCoordinator, workflow_id: str
    ) -> None:
        super().__init__(coordinator)
        self._workflow_id = workflow_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_wf_{workflow_id}"
        workflow = self._workflow
        # Entity name = workflow name under the n8n device (has_entity_name).
        self._attr_name = workflow.name if workflow else f"Workflow {workflow_id}"

    @property
    def _workflow(self) -> Workflow | None:
        return self.coordinator.get_workflow(self._workflow_id)

    @property
    def available(self) -> bool:
        """Return True when the coordinator has data and the workflow exists."""
        return (
            super().available
            and self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._workflow is not None
        )

    @property
    def is_on(self) -> bool:
        """Return True if the workflow is active in n8n."""
        workflow = self._workflow
        return bool(workflow and workflow.active)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return safe workflow metadata."""
        workflow = self._workflow
        if not workflow:
            return {ATTR_WORKFLOW_ID: self._workflow_id}
        return {
            ATTR_WORKFLOW_ID: workflow.workflow_id,
            ATTR_WORKFLOW_NAME: workflow.name,
            ATTR_TAGS: workflow.tags,
            "updated_at": workflow.updated_at,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate the workflow via the Public API."""
        try:
            await self.coordinator.client.async_activate_workflow(self._workflow_id)
        except N8nAuthError:
            raise
        except N8nApiError as err:
            _LOGGER.error("Failed to activate workflow %s: %s", self._workflow_id, err)
            raise
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate the workflow via the Public API."""
        try:
            await self.coordinator.client.async_deactivate_workflow(self._workflow_id)
        except N8nAuthError:
            raise
        except N8nApiError as err:
            _LOGGER.error(
                "Failed to deactivate workflow %s: %s", self._workflow_id, err
            )
            raise
        await self.coordinator.async_request_refresh()
