"""Unit tests for N8nApiClient (aiohttp mocked — no real credentials)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.n8n.api import (
    N8nApiClient,
    N8nApiError,
    N8nAuthError,
    N8nNotFoundError,
    workflow_from_api,
)


def _mock_response(
    status: int,
    payload: Any = None,
    *,
    content_type: str = "application/json",
    text: str = "",
) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.headers = {"Content-Type": content_type}
    response.json = AsyncMock(return_value=payload)
    response.text = AsyncMock(return_value=text)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _client_with_session(session: MagicMock) -> N8nApiClient:
    return N8nApiClient(session, "http://n8n:5678", "test-key", verify_ssl=True)


@pytest.mark.asyncio
async def test_validate_ok(workflows_list_payload: dict) -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=_mock_response(200, {"data": workflows_list_payload["data"][:1]})
    )
    client = _client_with_session(session)
    result = await client.async_validate()
    assert result["ok"] is True
    call_kwargs = session.request.call_args
    assert "X-N8N-API-KEY" in call_kwargs.kwargs["headers"]
    assert call_kwargs.kwargs["headers"]["X-N8N-API-KEY"] == "test-key"


@pytest.mark.asyncio
async def test_validate_auth_error() -> None:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(401, text="unauthorized"))
    client = _client_with_session(session)
    with pytest.raises(N8nAuthError):
        await client.async_validate()


@pytest.mark.asyncio
async def test_get_workflows(workflows_list_payload: dict) -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=_mock_response(200, workflows_list_payload)
    )
    client = _client_with_session(session)
    workflows = await client.async_get_workflows()
    assert len(workflows) == 2
    assert workflows[0].name == "Morning Lights"
    assert workflows[0].active is True
    assert workflows[0].webhook_path == "morning-lights"
    assert workflows[0].tags == ["home"]
    assert workflows[1].webhook_path is None
    assert workflows[1].trigger_mode == "api_execute"


@pytest.mark.asyncio
async def test_activate_deactivate() -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=_mock_response(
            200, {"id": "wf1", "name": "Morning Lights", "active": True}
        )
    )
    client = _client_with_session(session)
    activated = await client.async_activate_workflow("wf1")
    assert activated.active is True
    assert "activate" in session.request.call_args.args[1]


@pytest.mark.asyncio
async def test_trigger_prefers_webhook() -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=_mock_response(200, {"message": "Workflow was started"})
    )
    client = _client_with_session(session)
    result = await client.async_trigger_workflow(
        "wf1", webhook_path="morning-lights", data={"room": "kitchen"}
    )
    assert result["mode"] == "webhook"
    url = session.request.call_args.args[1]
    assert url.endswith("/webhook/morning-lights")
    # Webhook calls must not send the API key.
    assert "X-N8N-API-KEY" not in session.request.call_args.kwargs["headers"]


@pytest.mark.asyncio
async def test_trigger_falls_back_to_execute() -> None:
    detail = _mock_response(
        200,
        {
            "id": "wf2",
            "name": "No Webhook",
            "active": False,
            "nodes": [{"type": "n8n-nodes-base.manualTrigger", "parameters": {}}],
        },
    )
    execute = _mock_response(200, {"executionId": 9})
    session = MagicMock()
    session.request = MagicMock(side_effect=[detail, execute])
    client = _client_with_session(session)
    result = await client.async_trigger_workflow("wf2")
    assert result["mode"] == "api_execute"
    assert session.request.call_args.args[1].endswith("/workflows/wf2/execute")


@pytest.mark.asyncio
async def test_not_found() -> None:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(404, text="missing"))
    client = _client_with_session(session)
    with pytest.raises(N8nNotFoundError):
        await client.async_get_workflow("missing")


def test_workflow_from_api_without_nodes() -> None:
    wf = workflow_from_api({"id": 42, "name": "X", "active": False})
    assert wf.workflow_id == "42"
    assert wf.webhook_path is None


@pytest.mark.asyncio
async def test_connection_error_maps() -> None:
    import aiohttp

    session = MagicMock()

    class _FailingCM:
        async def __aenter__(self):
            raise aiohttp.ClientError("boom")

        async def __aexit__(self, *args):
            return None

    session.request = MagicMock(return_value=_FailingCM())
    client = _client_with_session(session)
    with pytest.raises(N8nApiError, match="Connection error"):
        await client.async_validate()
