"""Tests for config flow URL normalization (no live HA)."""

from __future__ import annotations

import pytest

from custom_components.n8n.config_flow import _normalize_base_url


def test_normalize_strips_slash() -> None:
    assert _normalize_base_url("http://n8n:5678/") == "http://n8n:5678"


def test_normalize_keeps_path_prefix() -> None:
    assert (
        _normalize_base_url("https://example.local/n8n/")
        == "https://example.local/n8n"
    )


def test_normalize_rejects_relative() -> None:
    with pytest.raises(ValueError):
        _normalize_base_url("n8n:5678")
