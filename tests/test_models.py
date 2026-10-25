"""Tests for n8n dataclasses."""

from custom_components.n8n.models import CoordinatorData, Workflow


def test_coordinator_lookup_and_dict() -> None:
    wf = Workflow(
        workflow_id="1",
        name="Demo",
        active=True,
        tags=["a"],
        webhook_path="demo",
    )
    data = CoordinatorData(workflows=[wf], reachable=True)
    assert data.workflow_by_id("1") is wf
    assert data.workflow_by_id("missing") is None
    as_dict = data.as_dict()
    assert as_dict["reachable"] is True
    assert as_dict["workflows"][0]["trigger_mode"] == "webhook"
    assert "api_key" not in str(as_dict)
