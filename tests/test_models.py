"""Tests for n8n dataclasses."""

from custom_components.n8n.models import CoordinatorData, ExecutionSummary, Workflow


def test_coordinator_lookup_and_dict() -> None:
    wf = Workflow(
        workflow_id="1",
        name="Demo",
        active=True,
        tags=["a"],
        webhook_path="demo",
    )
    last = ExecutionSummary(
        execution_id="e1",
        workflow_id="1",
        status="success",
        started_at="2026-01-01T00:00:00Z",
        mode="webhook",
    )
    data = CoordinatorData(
        workflows=[wf],
        reachable=True,
        last_executions={"1": last},
        failed_execution_count=2,
        execution_window_size=10,
    )
    assert data.workflow_by_id("1") is wf
    assert data.workflow_by_id("missing") is None
    assert data.last_execution("1") is last
    as_dict = data.as_dict()
    assert as_dict["reachable"] is True
    assert as_dict["failed_execution_count"] == 2
    assert as_dict["workflows"][0]["trigger_mode"] == "webhook"
    assert as_dict["last_executions"]["1"]["status"] == "success"
    assert "api_key" not in str(as_dict)
    assert "nodes" not in str(as_dict)
