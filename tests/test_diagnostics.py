"""Diagnostics redaction helpers (no Home Assistant install required)."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def async_redact_data(data: Any, to_redact: Iterable[str]) -> Any:
    """Minimal stand-in for homeassistant.components.diagnostics.async_redact_data."""
    redact = set(to_redact)
    if isinstance(data, Mapping):
        return {
            key: (
                "**REDACTED**"
                if key in redact
                else async_redact_data(value, redact)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [async_redact_data(item, redact) for item in data]
    return data


def test_redacts_secrets() -> None:
    from custom_components.n8n.diagnostics import TO_REDACT

    payload = {
        "entry": {
            "data": {
                "base_url": "http://n8n:5678",
                "api_key": "super-secret-key",
                "webhook_secret": "webhook-secret-value",
                "webhook_secrets": [
                    {
                        "id": "sec_1",
                        "label": "default",
                        "secret": "webhook-secret-value",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "webhook_id": "public-ish-id",
            }
        },
        "inbound_secret_count": 1,
        "inbound_secret_metadata": [
            {"id": "sec_1", "label": "default", "created_at": "2026-01-01T00:00:00Z"}
        ],
    }
    redacted = async_redact_data(payload, TO_REDACT)
    assert redacted["entry"]["data"]["api_key"] == "**REDACTED**"
    assert redacted["entry"]["data"]["webhook_secret"] == "**REDACTED**"
    assert redacted["entry"]["data"]["webhook_secrets"] == "**REDACTED**"
    assert redacted["entry"]["data"]["webhook_id"] == "public-ish-id"
    assert redacted["entry"]["data"]["base_url"] == "http://n8n:5678"
    assert redacted["inbound_secret_count"] == 1
    assert redacted["inbound_secret_metadata"][0]["id"] == "sec_1"
    assert "secret" not in redacted["inbound_secret_metadata"][0]
