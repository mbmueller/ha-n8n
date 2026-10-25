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
                "webhook_id": "public-ish-id",
            }
        }
    }
    redacted = async_redact_data(payload, TO_REDACT)
    assert redacted["entry"]["data"]["api_key"] == "**REDACTED**"
    assert redacted["entry"]["data"]["webhook_secret"] == "**REDACTED**"
    assert redacted["entry"]["data"]["webhook_id"] == "public-ish-id"
    assert redacted["entry"]["data"]["base_url"] == "http://n8n:5678"
