"""Unit tests for inbound webhook helpers (no live HA)."""

from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import make_mocked_request

from custom_components.n8n.const import WEBHOOK_HEADER
from custom_components.n8n.webhook import (
    N8nWebhookView,
    inbound_webhook_path,
)


def test_inbound_path() -> None:
    assert inbound_webhook_path("abc") == "/api/n8n/webhook/abc"


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret() -> None:
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        "webhook_id": "wid",
        "webhook_secret": "correct-secret",
    }
    hass.config_entries.async_entries.return_value = [entry]
    view = N8nWebhookView(hass)

    request = make_mocked_request(
        "POST",
        "/api/n8n/webhook/wid",
        headers={WEBHOOK_HEADER: "wrong"},
        payload=b"{}",
    )
    # make_mocked_request may not support payload the same on all versions
    request._body = b"{}"  # noqa: SLF001
    request.read = _async_return(b"{}")

    response = await view.post(request, "wid")
    assert response.status == HTTPStatus.UNAUTHORIZED
    hass.bus.async_fire.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_accepts_valid_secret() -> None:
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        "webhook_id": "wid",
        "webhook_secret": "correct-secret",
    }
    hass.config_entries.async_entries.return_value = [entry]
    view = N8nWebhookView(hass)

    body = json.dumps(
        {"event_type": "motion_cleared", "message": "ok", "room": "hall"}
    ).encode()
    request = make_mocked_request(
        "POST",
        "/api/n8n/webhook/wid",
        headers={WEBHOOK_HEADER: "correct-secret"},
    )
    request.read = _async_return(body)

    response = await view.post(request, "wid")
    assert response.status == 200
    hass.bus.async_fire.assert_called_once()
    event_name, event_data = hass.bus.async_fire.call_args.args
    assert event_name == "n8n_webhook_received"
    assert event_data["event_type"] == "motion_cleared"
    assert event_data["message"] == "ok"
    assert event_data["data"]["room"] == "hall"


@pytest.mark.asyncio
async def test_webhook_unknown_id() -> None:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = []
    view = N8nWebhookView(hass)
    request = make_mocked_request("POST", "/api/n8n/webhook/missing")
    request.read = _async_return(b"{}")
    response = await view.post(request, "missing")
    assert response.status == HTTPStatus.NOT_FOUND


def test_secret_compare_is_constant_time_compatible() -> None:
    a = secrets.token_urlsafe(16)
    assert secrets.compare_digest(a, a)
    assert not secrets.compare_digest(a, a + "x")


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
