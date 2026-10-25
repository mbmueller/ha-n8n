"""Unit tests for trigger service data / payload alias."""

from __future__ import annotations

from custom_components.n8n import trigger_body_from_service_data


def test_trigger_body_prefers_data() -> None:
    assert trigger_body_from_service_data(
        {"workflow_id": "1", "data": {"a": 1}, "payload": {"b": 2}}
    ) == {"a": 1}


def test_trigger_body_uses_payload_alias() -> None:
    assert trigger_body_from_service_data(
        {"workflow_id": "1", "payload": {"room": "kitchen"}}
    ) == {"room": "kitchen"}


def test_trigger_body_missing() -> None:
    assert trigger_body_from_service_data({"workflow_id": "1"}) is None
