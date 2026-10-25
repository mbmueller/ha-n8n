# ha-n8n

**Home Assistant custom integration for [n8n](https://n8n.io)** — bidirectional workflow triggers and a practical subset of the n8n Public API as HA entities.

> **Status:** Phase 2 (**v0.3.0**). Options (poll interval, allow/block lists), execution sensors, webhook path auto-discovery, multi-secret inbound webhooks, reauth/repair.

## What this is

A HACS-installable integration (`custom_components/n8n`) that lets you:

1. **HA → n8n** — discover workflows and activate / deactivate / trigger them from Home Assistant.
2. **n8n → HA** — POST from n8n to a secured HA webhook to fire `n8n_webhook_received` and update an event entity for automations.
3. **API as entities** — expose safe metadata (workflow state, last run, failures, connectivity) without leaking secrets.

Target deployment: **self-hosted n8n** and **Home Assistant Core ≥ 2026.9.3** in separate Docker containers on the same Raspberry Pi (LAN / Docker network).

## Requirements

| Component | Version / notes |
|-----------|-----------------|
| Home Assistant Core | **2026.9.3** or newer |
| n8n | Self-hosted with **Public API** enabled |
| HACS | Recommended for install & updates |

n8n Cloud is **not** a v1 target.

## Install (HACS)

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. **HACS → Integrations → ⋮ → Custom repositories**
3. Add this repository URL as category **Integration**:
   ```
   https://github.com/mbmueller/ha-n8n
   ```
4. Find **n8n** in HACS and install it.
5. Restart Home Assistant.
6. **Settings → Devices & services → Add integration → n8n**

### Manual install

Copy `custom_components/n8n` into your HA `custom_components/` directory, restart, then add the integration as above.

## Same-Pi Docker setup

Typical compose layout (names may differ):

| Container | Reachable as |
|-----------|----------------|
| Home Assistant | `http://homeassistant:8123` (from n8n) |
| n8n | `http://n8n:5678` (from HA) |

If containers are not on a shared user-defined network, use the host LAN IP or Docker gateway instead of service DNS names.

### Configure the integration

| Field | Description |
|-------|-------------|
| **n8n base URL** | e.g. `http://n8n:5678` on a shared Docker network |
| **API key** | Dedicated key from n8n **Settings → API** (`X-N8N-API-KEY`) |
| **Verify SSL** | Default on; disable only for trusted self-signed LAN certs |

The config flow validates with `GET /api/v1/workflows?limit=1`. On success, HA creates:

- One **device** for the n8n instance
- A **switch** / **button** / **last-run sensor** per exposed workflow
- `binary_sensor` **API** connectivity (diagnostic)
- `sensor` **Failed executions** (diagnostic aggregate)
- An **event** entity for inbound webhooks

**Do not** put API keys in YAML issues, screenshots, or git. HA stores config-entry secrets encrypted at rest.

## Options (Phase 2)

**Settings → Devices & services → n8n → Configure**:

| Option | Default | Notes |
|--------|---------|--------|
| Poll interval | `60` s | Clamped 30–300 |
| Workflow ID allowlist / blocklist | empty | Comma-separated ids |
| Tag allowlist / blocklist | empty | e.g. `ha-exposed` |
| Execution history window | `50` | Recent executions for last-run + failed count |
| Inbound secret action | `none` | `create` / `revoke` / `rotate` (see below) |

**Filtering:** empty allowlists expose **all** workflows (MVP default). If an id and/or tag allowlist is set, a workflow must match at least one allowlist. Blocklists always win.

Changing options reloads the entry.

## Entities & services

| Platform / service | Role |
|--------------------|------|
| `switch.*` | Activate / deactivate workflow via Public API |
| `button.*` | Trigger workflow once (no payload fields — use the service) |
| `sensor.*_last_run` | Last execution status per workflow (`success` / `error` / …) |
| `sensor.*_failed_executions` | Failed count in the recent execution window |
| `binary_sensor.*_api` | API reachability from the last poll |
| `event.*_inbound_webhook` | Last inbound n8n→HA webhook |
| `n8n.trigger_workflow` | Service: `workflow_id`, optional `data`/`payload`, `webhook_path`, `config_entry_id` |
| `n8n.refresh` | Force coordinator refresh |
| `n8n.activate_workflow` / `n8n.deactivate_workflow` | Explicit activate/deactivate |
| `n8n.create_inbound_secret` / `revoke_inbound_secret` / `rotate_inbound_secret` | Manage inbound webhook secrets |

## Inbound webhook (n8n → Home Assistant)

Each config entry has **one** unguessable webhook URL/path. **Multiple named shared secrets** can authenticate that same endpoint (like multiple API keys). Any valid secret in `X-N8N-HA-Secret` is accepted (constant-time compare against the active set).

**URL path (shared by all secrets):**

```text
POST /api/n8n/webhook/{webhook_id}
```

**Required header:**

```http
X-N8N-HA-Secret: <one active inbound secret>
```

On first setup HA shows a **persistent notification** with the URL and the initial secret — copy it into n8n credentials, then dismiss. **Existing secrets are never re-displayed** (not on entities, not in diagnostics). To get a value again, **create** or **rotate** a secret (the new value is shown once).

### Create a second secret (another n8n workflow)

Without reinstalling or changing the URL:

1. **Settings → Devices & services → n8n → Configure**
2. Set **Inbound secret action** to `create`, set a **label** (e.g. `kitchen-wf`), submit.
3. Open the new persistent notification, copy the secret into that workflow’s n8n credential.
4. Keep using the **same** webhook URL; only the header value differs per workflow.

Or via service:

```yaml
action: n8n.create_inbound_secret
data:
  label: kitchen-wf
```

### Revoke / rotate

- **Revoke:** options action `revoke` + secret id, or `n8n.revoke_inbound_secret` with `secret_id`. The last remaining secret cannot be revoked.
- **Rotate:** options action `rotate` (creates a new secret, shows it once, and by default revokes all previous secrets). Or `n8n.rotate_inbound_secret`. Pass `revoke_secret_id` to revoke one previous secret instead of all.

After repeated auth failures HA may open a **repair** flow that rotates secrets the same way.

### Example body

```json
{
  "event_type": "motion_cleared",
  "message": "Front hall quiet",
  "source": "hallway-cam"
}
```

On success HA fires bus event `n8n_webhook_received` and updates the inbound **event** entity.

### Example: n8n HTTP Request node (same Docker network)

| Setting | Value |
|---------|--------|
| Method | `POST` |
| URL | `http://homeassistant:8123/api/n8n/webhook/YOUR_WEBHOOK_ID` |
| Header | `X-N8N-HA-Secret` = one active secret (store in n8n **Credentials**) |
| Body | JSON as above |

### Example automation trigger (YAML)

```yaml
alias: React to n8n webhook
triggers:
  - trigger: event
    event_type: n8n_webhook_received
conditions: []
actions:
  - action: notify.persistent_notification
    data:
      message: "{{ trigger.event.data.message }}"
```

## Triggering workflows from HA

Buttons / `n8n.trigger_workflow` use this order:

1. Known **Webhook** node production path (`POST {base_url}/webhook/{path}`), auto-discovered from workflow JSON in coordinator memory (node graphs are **not** dumped into entity attributes).
2. Else Public API **`POST /api/v1/workflows/{id}/execute`** (when your n8n build supports it).

### Passing data (JSON body)

HA **button** entities cannot take fields. Call **`n8n.trigger_workflow`** with `data` (or alias `payload`):

```yaml
action: n8n.trigger_workflow
data:
  workflow_id: "AbCdEf123"
  data:
    room: kitchen
    brightness: 80
```

## Migration notes (existing installs)

Upgrading from Phase 1 (`≤0.2.x`) to **0.3.0**:

- The single `webhook_secret` is migrated into a multi-secret list automatically; the same value keeps working — **no action required** for inbound webhooks.
- All workflows remain exposed until you set allowlists in options.
- New sensors (`last run`, `failed executions`) appear after reload/restart.
- Poll interval defaults to 60s until changed in options.
- Reauth still works when the API key is rejected (401/403).

## Security notes

- API keys and webhook secrets must never appear in entity attributes, issue reports, or unredacted diagnostics (diagnostics may show **secret count** and id/label metadata only).
- Prefer HTTPS for any non-localhost n8n URL.
- A compromised HA backup can expose n8n API keys and inbound secrets — rotate/revoke if that happens.
- Inbound webhooks require a valid shared secret header; reject missing/invalid secrets with `401`.

## Diagnostics

**Settings → Devices & services → n8n → Download diagnostics** returns redacted config, coordinator snapshot, inbound webhook **path**, and inbound secret **metadata** (id/label/created_at — values redacted).

## Roadmap (short)

| Phase | Focus |
|-------|--------|
| **0** | HACS packaging, config-flow stub |
| **1** | Live API client, switches/buttons, inbound webhook + event entity |
| **2** (this release) | Options, execution sensors, webhook discovery, multi-secret inbound, reauth/repair |
| **3+** | Credential metadata sensors, MQTT inbound, Core submission |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Marlon Müller

## Links

- Issues: https://github.com/mbmueller/ha-n8n/issues
- n8n Public API: https://docs.n8n.io/api/
- Home Assistant custom integrations: https://developers.home-assistant.io/docs/creating_integration_file_structure/
