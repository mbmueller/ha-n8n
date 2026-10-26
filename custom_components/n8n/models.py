"""Dataclasses for n8n API payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Workflow:
    """Safe workflow metadata exposed to Home Assistant."""

    workflow_id: str
    name: str
    active: bool
    tags: list[str] = field(default_factory=list)
    updated_at: str | None = None
    webhook_path: str | None = None

    @property
    def trigger_mode(self) -> str:
        """How HA can trigger this workflow."""
        return "webhook" if self.webhook_path else "api_execute"


@dataclass(slots=True)
class ExecutionSummary:
    """Safe execution metadata (never includes run data / secrets)."""

    execution_id: str
    workflow_id: str | None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    mode: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for diagnostics / entity attributes."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "mode": self.mode,
        }


@dataclass(slots=True)
class CoordinatorData:
    """Payload stored on the DataUpdateCoordinator."""

    workflows: list[Workflow] = field(default_factory=list)
    reachable: bool = False
    last_executions: dict[str, ExecutionSummary] = field(default_factory=dict)
    failed_execution_count: int = 0
    execution_window_size: int = 0

    def workflow_by_id(self, workflow_id: str) -> Workflow | None:
        """Return a workflow by id, if present."""
        for workflow in self.workflows:
            if workflow.workflow_id == workflow_id:
                return workflow
        return None

    def last_execution(self, workflow_id: str) -> ExecutionSummary | None:
        """Return the most recent execution summary for a workflow."""
        return self.last_executions.get(workflow_id)

    def as_dict(self) -> dict[str, Any]:
        """Serialize for diagnostics / debugging (no secrets, no node graphs)."""
        return {
            "reachable": self.reachable,
            "failed_execution_count": self.failed_execution_count,
            "execution_window_size": self.execution_window_size,
            "workflows": [
                {
                    "id": w.workflow_id,
                    "name": w.name,
                    "active": w.active,
                    "tags": w.tags,
                    "updated_at": w.updated_at,
                    "webhook_path": w.webhook_path,
                    "trigger_mode": w.trigger_mode,
                }
                for w in self.workflows
            ],
            "last_executions": {
                wid: summary.as_dict()
                for wid, summary in self.last_executions.items()
            },
        }
