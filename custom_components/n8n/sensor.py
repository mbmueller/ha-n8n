"""Sensor platform: last execution status and failed-execution aggregate."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EXECUTION_ID,
    ATTR_FINISHED_AT,
    ATTR_MODE,
    ATTR_STARTED_AT,
    ATTR_STATUS,
    ATTR_TAGS,
    ATTR_WORKFLOW_ID,
    ATTR_WORKFLOW_NAME,
    DOMAIN,
)
from .coordinator import N8nDataUpdateCoordinator
from .entity import N8nEntity
from .models import ExecutionSummary, Workflow

FAILED_EXECUTIONS_DESCRIPTION = SensorEntityDescription(
    key="failed_executions",
    translation_key="failed_executions",
    entity_category=EntityCategory.DIAGNOSTIC,
    native_unit_of_measurement="executions",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up n8n execution sensors."""
    coordinator: N8nDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    known: set[str] = set()

    async_add_entities([N8nFailedExecutionsSensor(coordinator)])

    @callback
    def _async_add_from_coordinator() -> None:
        if not coordinator.data:
            return
        new_entities: list[N8nLastExecutionSensor] = []
        for workflow in coordinator.data.workflows:
            if workflow.workflow_id in known:
                continue
            known.add(workflow.workflow_id)
            new_entities.append(
                N8nLastExecutionSensor(coordinator, workflow.workflow_id)
            )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_from_coordinator()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_from_coordinator))


class N8nFailedExecutionsSensor(N8nEntity, SensorEntity):
    """Count of failed executions in the recent Public API window."""

    entity_description = FAILED_EXECUTIONS_DESCRIPTION

    def __init__(self, coordinator: N8nDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_failed_executions"
        self._attr_name = "Failed executions"

    @property
    def native_value(self) -> int:
        """Return failed execution count from the last poll window."""
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.failed_execution_count)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the window size used for the aggregate."""
        data = self.coordinator.data
        return {
            "window_size": data.execution_window_size if data else 0,
            "window_limit": (
                self.coordinator.entry.options.get("execution_history_limit")
                if self.coordinator.entry.options
                else None
            ),
        }


class N8nLastExecutionSensor(N8nEntity, SensorEntity):
    """Last execution status for a single workflow."""

    _attr_translation_key = "last_execution"

    def __init__(
        self, coordinator: N8nDataUpdateCoordinator, workflow_id: str
    ) -> None:
        super().__init__(coordinator)
        self._workflow_id = workflow_id
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_last_run_{workflow_id}"
        )
        workflow = self._workflow
        name = workflow.name if workflow else workflow_id
        self._attr_name = f"{name} last run"

    @property
    def _workflow(self) -> Workflow | None:
        return self.coordinator.get_workflow(self._workflow_id)

    @property
    def _execution(self) -> ExecutionSummary | None:
        return self.coordinator.get_last_execution(self._workflow_id)

    @property
    def available(self) -> bool:
        """Unavailable when the workflow is filtered out or API is down."""
        return (
            super().available
            and self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._workflow is not None
        )

    @property
    def native_value(self) -> str:
        """Return last execution status or unknown."""
        execution = self._execution
        if execution is None:
            return "unknown"
        return execution.status or "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Safe execution metadata (never node graphs or run data)."""
        workflow = self._workflow
        execution = self._execution
        attrs: dict[str, Any] = {
            ATTR_WORKFLOW_ID: self._workflow_id,
            ATTR_WORKFLOW_NAME: workflow.name if workflow else None,
            ATTR_TAGS: workflow.tags if workflow else [],
        }
        if execution is None:
            attrs[ATTR_STATUS] = "unknown"
            return attrs
        attrs.update(
            {
                ATTR_EXECUTION_ID: execution.execution_id,
                ATTR_STATUS: execution.status,
                ATTR_STARTED_AT: execution.started_at,
                ATTR_FINISHED_AT: execution.finished_at,
                ATTR_MODE: execution.mode,
            }
        )
        return attrs
