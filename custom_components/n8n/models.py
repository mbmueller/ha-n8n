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
class CoordinatorData:
    """Payload stored on the DataUpdateCoordinator."""

    workflows: list[Workflow] = field(default_factory=list)
    reachable: bool = False

    def workflow_by_id(self, workflow_id: str) -> Workflow | None:
        """Return a workflow by id, if present."""
        for workflow in self.workflows:
            if workflow.workflow_id == workflow_id:
                return workflow
        return None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for diagnostics / debugging (no secrets)."""
        return {
            "reachable": self.reachable,
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
        }
