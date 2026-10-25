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
from custom_components.n8n.webhook_secrets import add_secret


def test_inbound_path() -> None:
    assert inbound_webhook_path("abc") == "/api/n8n/webhook/abc"


def _entry_with_secrets(*secret_values: str) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry1"
    data: dict = {"webhook_id": "wid"}
    for i, value in enumerate(secret_values):
        data, record = add_secret(data, f"s{i}")
        record["secret"] = value
        data["webhook_secrets"][-1] = record
    entry.data = data
    return entry


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret() -> None:
    hass = MagicMock()
    hass.data = {}
    entry = _entry_with_secrets("correct-secret")
    hass.config_entries.async_entries.return_value = [entry]
    view = N8nWebhookView(hass)

    request = make_mocked_request(
        "POST",
        "/api/n8n/webhook/wid",
        headers={WEBHOOK_HEADER: "wrong"},
    )
    request.read = _async_return(b"{}")

    response = await view.post(request, "wid")
    assert response.status == HTTPStatus.UNAUTHORIZED
    hass.bus.async_fire.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_accepts_any_active_secret() -> None:
    hass = MagicMock()
    hass.data = {}
    entry = _entry_with_secrets("secret-a", "secret-b")
    hass.config_entries.async_entries.return_value = [entry]
    view = N8nWebhookView(hass)

    body = json.dumps(
        {"event_type": "motion_cleared", "message": "ok", "room": "hall"}
    ).encode()
    request = make_mocked_request(
        "POST",
        "/api/n8n/webhook/wid",
        headers={WEBHOOK_HEADER: "secret-b"},
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
    assert event_data["secret_count"] == 2


@pytest.mark.asyncio
async def test_webhook_accepts_legacy_migrated_shape() -> None:
    """Entries still carrying only webhook_secrets list work."""
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.data = {
        "webhook_id": "wid",
        "webhook_secrets": [
            {
                "id": "sec_x",
                "label": "default",
                "secret": "correct-secret",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    }
    hass.config_entries.async_entries.return_value = [entry]
    view = N8nWebhookView(hass)
    request = make_mocked_request(
        "POST",
        "/api/n8n/webhook/wid",
        headers={WEBHOOK_HEADER: "correct-secret"},
    )
    request.read = _async_return(b"{}")
    response = await view.post(request, "wid")
    assert response.status == 200


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
