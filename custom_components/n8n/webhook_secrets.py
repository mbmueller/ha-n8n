"""Inbound webhook multi-secret store (create / revoke / rotate)."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from homeassistant.util import dt as dt_util

from .const import CONF_WEBHOOK_SECRET, CONF_WEBHOOK_SECRETS

_LOGGER = logging.getLogger(__name__)


def new_secret_record(label: str | None = None) -> dict[str, str]:
    """Create a new secret record (plaintext secret included once for the caller)."""
    cleaned = (label or "").strip() or "default"
    return {
        "id": f"sec_{secrets.token_urlsafe(9)}",
        "label": cleaned[:64],
        "secret": secrets.token_urlsafe(24),
        "created_at": dt_util.utcnow().isoformat(),
    }


def list_webhook_secrets(entry_data: dict[str, Any]) -> list[dict[str, str]]:
    """Return normalized secret records from config entry data."""
    raw = entry_data.get(CONF_WEBHOOK_SECRETS)
    records: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            secret = item.get("secret")
            sid = item.get("id")
            if not secret or not sid:
                continue
            records.append(
                {
                    "id": str(sid),
                    "label": str(item.get("label") or "default")[:64],
                    "secret": str(secret),
                    "created_at": str(item.get("created_at") or ""),
                }
            )
    return records


def migrate_webhook_secrets(entry_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Ensure ``webhook_secrets`` exists; migrate legacy single ``webhook_secret``.

    Returns (updated_data, changed).
    """
    data = dict(entry_data)
    existing = list_webhook_secrets(data)
    if existing:
        # Drop legacy plaintext twin once the list is authoritative.
        if CONF_WEBHOOK_SECRET in data:
            data.pop(CONF_WEBHOOK_SECRET, None)
            return data, True
        return data, False

    legacy = data.get(CONF_WEBHOOK_SECRET)
    if legacy:
        record = {
            "id": f"sec_{secrets.token_urlsafe(9)}",
            "label": "default",
            "secret": str(legacy),
            "created_at": dt_util.utcnow().isoformat(),
        }
        data[CONF_WEBHOOK_SECRETS] = [record]
        data.pop(CONF_WEBHOOK_SECRET, None)
        _LOGGER.info("Migrated legacy inbound webhook secret to multi-secret store")
        return data, True

    record = new_secret_record("default")
    data[CONF_WEBHOOK_SECRETS] = [record]
    data.pop(CONF_WEBHOOK_SECRET, None)
    return data, True


def secret_values(entry_data: dict[str, Any]) -> list[str]:
    """Return plaintext secret strings currently accepted."""
    return [r["secret"] for r in list_webhook_secrets(entry_data)]


def secret_matches(provided: str, entry_data: dict[str, Any]) -> bool:
    """Constant-time compare ``provided`` against every stored secret."""
    candidates = secret_values(entry_data)
    if not candidates:
        return False
    # Pad provided comparisons so we always scan the full set (no early exit).
    matched = False
    provided_str = str(provided)
    for candidate in candidates:
        # compare_digest requires equal-length strings; length mismatch is not a match.
        if len(provided_str) == len(candidate) and secrets.compare_digest(
            provided_str, candidate
        ):
            matched = True
        else:
            # Still perform a dummy compare of equal length to reduce timing skew.
            dummy = candidate
            secrets.compare_digest(dummy, dummy)
    return matched


def add_secret(
    entry_data: dict[str, Any], label: str | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    """Append a new secret; return (updated entry data, new record)."""
    data = dict(entry_data)
    records = list_webhook_secrets(data)
    record = new_secret_record(label)
    records.append(record)
    data[CONF_WEBHOOK_SECRETS] = records
    data.pop(CONF_WEBHOOK_SECRET, None)
    return data, record


def revoke_secret(
    entry_data: dict[str, Any], secret_id: str
) -> tuple[dict[str, Any], bool]:
    """Remove a secret by id. Returns (data, removed?). Refuses to remove the last secret."""
    data = dict(entry_data)
    records = list_webhook_secrets(data)
    if len(records) <= 1:
        return data, False
    remaining = [r for r in records if r["id"] != secret_id]
    if len(remaining) == len(records):
        return data, False
    if not remaining:
        return data, False
    data[CONF_WEBHOOK_SECRETS] = remaining
    data.pop(CONF_WEBHOOK_SECRET, None)
    return data, True


def rotate_secrets(
    entry_data: dict[str, Any],
    *,
    label: str | None = None,
    revoke_id: str | None = None,
    revoke_all_others: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Create a new secret and optionally revoke one or all previous secrets."""
    data, record = add_secret(entry_data, label)
    if revoke_all_others:
        data[CONF_WEBHOOK_SECRETS] = [record]
    elif revoke_id:
        data, _ = revoke_secret(data, revoke_id)
        # Ensure the new secret survived revoke (it should — different id).
        if not any(r["id"] == record["id"] for r in list_webhook_secrets(data)):
            data[CONF_WEBHOOK_SECRETS] = list_webhook_secrets(data) + [record]
    return data, record


def secrets_public_metadata(entry_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Metadata safe for diagnostics / entity attributes (no secret values)."""
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "created_at": r["created_at"],
        }
        for r in list_webhook_secrets(entry_data)
    ]
