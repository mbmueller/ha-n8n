# ha-n8n

**Home Assistant custom integration for [n8n](https://n8n.io)** — bidirectional workflow triggers and a practical subset of the n8n Public API as HA entities.

> **Status:** Phase 1 MVP (**v0.2.0**). Config flow validates against the n8n Public API; workflows appear as switches/buttons; inbound n8n→HA webhooks fire bus events and an event entity.

## What this is

A HACS-installable integration (`custom_components/n8n`) that lets you:

1. **HA → n8n** — discover all workflows and activate / deactivate / trigger them from Home Assistant.
2. **n8n → HA** — POST from n8n to a secured HA webhook to fire `n8n_webhook_received` and update an event entity for automations.
3. **API as entities** — expose safe metadata (workflow state, connectivity) without leaking secrets.

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
- A **switch** per workflow (active / inactive)
- A **button** per workflow (run once)
- `binary_sensor` **API** connectivity (diagnostic)
- An **event** entity for inbound webhooks

**Do not** put API keys in YAML issues, screenshots, or git. HA stores config-entry secrets encrypted at rest.

## Entities & services

| Platform / service | Role |
|--------------------|------|
| `switch.*` | Activate / deactivate workflow via Public API |
| `button.*` | Trigger workflow (webhook path if present, else API `/execute`) |
| `binary_sensor.*_api` | API reachability from the last poll |
| `event.*_inbound_webhook` | Last inbound n8n→HA webhook |
| `n8n.trigger_workflow` | Service: `workflow_id`, optional `data`, `webhook_path`, `config_entry_id` |
| `n8n.refresh` | Force coordinator refresh |
| `n8n.activate_workflow` / `n8n.deactivate_workflow` | Explicit activate/deactivate |

### MVP success path (from HA UI)

1. Open the n8n device → turn a workflow **switch off** (deactivated in n8n).
2. Press another workflow **Run** button (or call `n8n.trigger_workflow`).
3. From n8n, POST to the inbound HA webhook (below) and confirm an automation / the event entity updates.

## Inbound webhook (n8n → Home Assistant)

Each config entry gets an unguessable webhook id and shared secret. On first setup HA shows a **persistent notification** with the full URL and `X-N8N-HA-Secret` value — copy them into n8n credentials, then dismiss the notice (it is only created once).

The inbound **event** entity also exposes `webhook_path` and `auth_header` attributes (never the secret). Diagnostics include the path with secrets redacted.

**URL path:**

```text
POST /api/n8n/webhook/{webhook_id}
```

**Required header:**

```http
X-N8N-HA-Secret: <webhook_secret from the setup notification>
```

**Example body:**

```json
{
  "event_type": "motion_cleared",
  "message": "Front hall quiet",
  "source": "hallway-cam"
}
```

On success HA:

1. Fires bus event `n8n_webhook_received` with `entry_id`, `event_type`, `message`, `data`, …
2. Updates the inbound **event** entity (usable in the Automations UI).

### Example: n8n HTTP Request node (same Docker network)

| Setting | Value |
|---------|--------|
| Method | `POST` |
| URL | `http://homeassistant:8123/api/n8n/webhook/YOUR_WEBHOOK_ID` |
| Header | `X-N8N-HA-Secret` = your shared secret (store in n8n **Credentials**, not hard-coded) |
| Body | JSON as above |

If HA is only on the host network, try `http://172.17.0.1:8123/...` or the Pi’s LAN IP from the n8n container.

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

Or use the **Event entity** trigger on `event.n8n_*_inbound_webhook`.

## Triggering workflows from HA

Buttons / `n8n.trigger_workflow` use this order:

1. Known **Webhook** node production path (`POST {base_url}/webhook/{path}`), discovered from workflow nodes when available.
2. Else Public API **`POST /api/v1/workflows/{id}/execute`** (when your n8n build supports it).

For reliable “run now” on older n8n versions, add a **Webhook** trigger to the workflow and activate it.

Optional service payload:

```yaml
action: n8n.trigger_workflow
data:
  workflow_id: "AbCdEf123"
  data:
    room: kitchen
    brightness: 80
```

## Security notes

- API keys and webhook secrets must never appear in entity attributes, issue reports, or unredacted diagnostics.
- Prefer HTTPS for any non-localhost n8n URL.
- A compromised HA backup can expose the n8n API key and inbound webhook secret — rotate both if that happens.
- Inbound webhooks require the shared secret header; reject missing/invalid secrets with `401`.
- Put the HA webhook secret in the n8n credential store when possible.

## Diagnostics

**Settings → Devices & services → n8n → Download diagnostics** returns redacted config (API key / webhook secret scrubbed), coordinator snapshot, and the inbound webhook **path** (not the secret).

## Roadmap (short)

| Phase | Focus |
|-------|--------|
| **0** | HACS packaging, config-flow stub |
| **1** (this release) | Live API client, coordinator, switches/buttons, inbound webhook + event entity, diagnostics, EN/DE strings |
| **2+** | Options (poll interval, allowlists), execution sensors, webhook auto-discovery polish |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Marlon Müller

## Links

- Issues: https://github.com/mbmueller/ha-n8n/issues
- n8n Public API: https://docs.n8n.io/api/
- Home Assistant custom integrations: https://developers.home-assistant.io/docs/creating_integration_file_structure/
