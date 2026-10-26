# Contributing to ha-n8n

Thanks for helping with the Home Assistant ↔ n8n bridge. This project is early (Phase 0 scaffold); keep changes focused and secret-free.

## Ground rules

1. **No secrets in the repo or issues.** Never commit API keys, webhook secrets, `.env` files, HA `secrets.yaml`, or real hostnames/tokens in fixtures. Sanitize logs and screenshots.
2. **Self-hosted first.** Design and docs assume n8n + HA on the same LAN/Docker network (HA Core ≥ 2026.9.3). Do not optimize PRs for n8n Cloud unless discussed.
3. **HA patterns.** Prefer config entries, config/options flows, `DataUpdateCoordinator`, and platform entities over ad-hoc YAML or shell hacks.
4. **Small PRs.** One concern per PR (API client, config flow, a single platform, docs, tests).

## Development setup

1. Fork and clone this repository.
2. Symlink or copy `custom_components/n8n` into a Home Assistant `config/custom_components/` directory (or use a dedicated HA Docker bind-mount).
3. Restart HA after Python changes; clear browser cache if the config flow UI looks stale.
4. Use a **dedicated** n8n API key on a non-production instance when exercising live calls.

Unit tests (mocked aiohttp; no live credentials):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

GitHub Actions runs the same `pytest` command on every pull request and on pushes to `main` (see `.github/workflows/ci.yml`). A failing test fails the PR check.

Full Home Assistant integration tests (optional) need HA Core ≥ 2026.9.3 and `pytest-homeassistant-custom-component`.

## Code style

- Match Home Assistant custom-integration conventions (async everywhere for I/O, typed where practical).
- Do not log API keys, `Authorization` / `X-N8N-API-KEY` headers, or execution bodies that may contain PII.
- Entity state/attributes must never include credential secret material — metadata only (id, name, type).
- Keep the integration domain `n8n` and package path `custom_components/n8n`.

## Pull requests

- Describe **what** changed and **why** (link issues when relevant).
- Note how you tested (HA version, n8n version, mocked vs live).
- Update `README.md` / `strings.json` / `translations/` when user-visible behavior changes.
- Bump `version` in `manifest.json` only when cutting a release (maintainers).

## Reporting bugs

Include:

- Home Assistant Core version
- Integration version (`manifest.json` / HACS)
- n8n version (self-hosted) and whether Public API is enabled
- Steps to reproduce and sanitized logs

Omit API keys, webhook secrets, and full workflow JSON that may embed credentials.

## License

By contributing, you agree your contributions are licensed under the MIT License (see [LICENSE](LICENSE)).
