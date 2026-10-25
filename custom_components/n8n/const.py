"""Constants for the n8n integration."""

from __future__ import annotations

DOMAIN = "n8n"

# Platforms will be enabled as features land (Phase 1+).
PLATFORMS: list[str] = []

DEFAULT_SCAN_INTERVAL = 60
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_VERIFY_SSL = True
