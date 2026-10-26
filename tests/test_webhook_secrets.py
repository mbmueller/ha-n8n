"""Unit tests for multi-secret inbound webhook store."""

from __future__ import annotations

from custom_components.n8n.webhook_secrets import (
    add_secret,
    list_webhook_secrets,
    migrate_webhook_secrets,
    revoke_secret,
    rotate_secrets,
    secret_matches,
    secrets_public_metadata,
)


def test_migrate_legacy_single_secret() -> None:
    data, changed = migrate_webhook_secrets({"webhook_secret": "legacy-secret"})
    assert changed is True
    secrets = list_webhook_secrets(data)
    assert len(secrets) == 1
    assert secrets[0]["secret"] == "legacy-secret"
    assert secrets[0]["label"] == "default"
    assert "webhook_secret" not in data


def test_migrate_creates_default_when_empty() -> None:
    data, changed = migrate_webhook_secrets({})
    assert changed is True
    assert len(list_webhook_secrets(data)) == 1


def test_add_and_match_multiple_secrets() -> None:
    data, first = add_secret({}, "alpha")
    data, second = add_secret(data, "beta")
    assert secret_matches(first["secret"], data)
    assert secret_matches(second["secret"], data)
    assert not secret_matches("wrong", data)
    meta = secrets_public_metadata(data)
    assert all("secret" not in m for m in meta)
    assert {m["label"] for m in meta} == {"alpha", "beta"}


def test_revoke_refuses_last_secret() -> None:
    data, record = add_secret({}, "only")
    data2, removed = revoke_secret(data, record["id"])
    assert removed is False
    assert len(list_webhook_secrets(data2)) == 1


def test_revoke_one_of_many() -> None:
    data, a = add_secret({}, "a")
    data, b = add_secret(data, "b")
    data, removed = revoke_secret(data, a["id"])
    assert removed is True
    assert secret_matches(b["secret"], data)
    assert not secret_matches(a["secret"], data)


def test_rotate_revokes_all_others() -> None:
    data, old = add_secret({}, "old")
    data, new = rotate_secrets(data, label="new", revoke_all_others=True)
    assert len(list_webhook_secrets(data)) == 1
    assert secret_matches(new["secret"], data)
    assert not secret_matches(old["secret"], data)


def test_rotate_revokes_specific() -> None:
    data, a = add_secret({}, "a")
    data, b = add_secret(data, "b")
    data, new = rotate_secrets(data, label="c", revoke_id=a["id"])
    assert secret_matches(new["secret"], data)
    assert secret_matches(b["secret"], data)
    assert not secret_matches(a["secret"], data)
