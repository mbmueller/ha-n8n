"""Constants for the n8n integration."""

from __future__ import annotations

DOMAIN = "n8n"

PLATFORMS: list[str] = [
    "switch",
    "button",
    "binary_sensor",
    "sensor",
    "event",
]

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300

CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_VERIFY_SSL = "verify_ssl"
CONF_WEBHOOK_ID = "webhook_id"
CONF_WEBHOOK_SECRET = "webhook_secret"  # legacy single secret (migrated away)
CONF_WEBHOOK_SECRETS = "webhook_secrets"  # list[{id, label, secret, created_at}]

# Options (Phase 2)
CONF_SCAN_INTERVAL = "scan_interval"
CONF_WORKFLOW_ALLOWLIST = "workflow_allowlist"
CONF_WORKFLOW_BLOCKLIST = "workflow_blocklist"
CONF_TAG_ALLOWLIST = "tag_allowlist"
CONF_TAG_BLOCKLIST = "tag_blocklist"
CONF_EXECUTION_HISTORY_LIMIT = "execution_history_limit"

# Inbound secret management (options / services)
CONF_INBOUND_SECRET_ACTION = "inbound_secret_action"
CONF_INBOUND_SECRET_LABEL = "inbound_secret_label"
CONF_INBOUND_SECRET_ID = "inbound_secret_id"
INBOUND_SECRET_ACTION_NONE = "none"
INBOUND_SECRET_ACTION_CREATE = "create"
INBOUND_SECRET_ACTION_REVOKE = "revoke"
INBOUND_SECRET_ACTION_ROTATE = "rotate"

DEFAULT_VERIFY_SSL = True
DEFAULT_EXECUTION_HISTORY_LIMIT = 50
MAX_EXECUTION_HISTORY_LIMIT = 250

ATTR_WORKFLOW_ID = "workflow_id"
ATTR_WORKFLOW_NAME = "workflow_name"
ATTR_TAGS = "tags"
ATTR_WEBHOOK_PATH = "webhook_path"
ATTR_TRIGGER_MODE = "trigger_mode"
ATTR_EXECUTION_ID = "execution_id"
ATTR_STARTED_AT = "started_at"
ATTR_FINISHED_AT = "finished_at"
ATTR_MODE = "mode"
ATTR_STATUS = "status"

EVENT_WEBHOOK_RECEIVED = "n8n_webhook_received"

WEBHOOK_HEADER = "X-N8N-HA-Secret"
MAX_WEBHOOK_PAYLOAD_BYTES = 65536

# Repair / inbound webhook health
ISSUE_STALE_INBOUND_WEBHOOK = "stale_inbound_webhook"
WEBHOOK_AUTH_FAILURE_THRESHOLD = 5

MANUFACTURER = "n8n"
