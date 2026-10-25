"""Constants for the n8n integration."""

from __future__ import annotations

DOMAIN = "n8n"

PLATFORMS: list[str] = [
    "switch",
    "button",
    "binary_sensor",
    "event",
]

DEFAULT_SCAN_INTERVAL = 60
CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_VERIFY_SSL = "verify_ssl"
CONF_WEBHOOK_ID = "webhook_id"
CONF_WEBHOOK_SECRET = "webhook_secret"

DEFAULT_VERIFY_SSL = True

ATTR_WORKFLOW_ID = "workflow_id"
ATTR_WORKFLOW_NAME = "workflow_name"
ATTR_TAGS = "tags"
ATTR_WEBHOOK_PATH = "webhook_path"
ATTR_TRIGGER_MODE = "trigger_mode"

EVENT_WEBHOOK_RECEIVED = "n8n_webhook_received"

WEBHOOK_HEADER = "X-N8N-HA-Secret"
MAX_WEBHOOK_PAYLOAD_BYTES = 65536

MANUFACTURER = "n8n"
