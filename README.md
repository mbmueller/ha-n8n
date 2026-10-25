# ha-n8n

**Home Assistant custom integration for [n8n](https://n8n.io)** — bidirectional workflow triggers and a practical subset of the n8n Public API as HA entities.

> **Status:** Early / Phase 0 scaffold. The integration loads as a HACS custom component and exposes a config flow stub. Live API polling, entities, and inbound webhooks are not implemented yet.

## What this is

A HACS-installable integration (`custom_components/n8n`) that will let you:

1. **HA → n8n** — discover workflows and start / activate / deactivate them from Home Assistant (entities, services, automations).
2. **n8n → HA** — fire Home Assistant events from n8n (secure inbound webhook) so automations can react.
3. **API as entities** — expose safe metadata (workflow state, execution summaries, connectivity) without leaking secrets.

Target deployment: **self-hosted n8n** and **Home Assistant Core ≥ 2026.9.3** in separate Docker containers on the same host (LAN / Docker network).

## Requirements

| Component | Version / notes |
|-----------|-----------------|
| Home Assistant Core | **2026.9.3** or newer |
| n8n | Self-hosted with Public API enabled |
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

## Configuration

Config flow fields (Phase 0 stores them; live validation comes later):

| Field | Description |
|-------|-------------|
| **n8n base URL** | e.g. `http://n8n:5678` on Docker, or your LAN HTTPS URL |
| **API key** | Dedicated key from n8n **Settings → API** (least privilege) |
| **Verify SSL** | Default on; disable only for trusted self-signed LAN certs |

**Do not** put API keys in YAML issues, screenshots, or git. HA stores config-entry secrets encrypted at rest.

## Security notes

- API keys and webhook secrets must never appear in entity attributes, issue reports, or diagnostics without redaction.
- Prefer HTTPS for any non-localhost n8n URL.
- A compromised HA backup can expose the n8n API key — rotate keys if that happens.
- Inbound webhooks (upcoming) will require an unguessable path id **and** a shared secret header.

## Roadmap (short)

| Phase | Focus |
|-------|--------|
| **0** (this repo) | HACS packaging, config-flow stub, MIT license, docs |
| **1** | Live API client, coordinator, switches/buttons, inbound webhook + event entity |
| **2+** | Options (poll interval, allowlists), execution sensors, reauth, polish |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome once Phase 1 work begins in earnest.

## License

[MIT](LICENSE) © 2026 Marlon Müller

## Links

- Issues: https://github.com/mbmueller/ha-n8n/issues
- n8n Public API: https://docs.n8n.io/api/
- Home Assistant custom integrations: https://developers.home-assistant.io/docs/creating_integration_file_structure/
