"""Repair flows for the n8n integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_WEBHOOK_ID, DOMAIN, ISSUE_STALE_INBOUND_WEBHOOK
from .webhook import (
    async_notify_new_inbound_secret,
    inbound_webhook_path,
    reset_webhook_auth_failures,
)
from .webhook_secrets import rotate_secrets

_LOGGER = logging.getLogger(__name__)


async def async_create_fix(
    hass: HomeAssistant,
    issue_id: str,
) -> RepairsFlow:
    """Create a repair flow for a registered issue."""
    if issue_id.startswith(f"{ISSUE_STALE_INBOUND_WEBHOOK}_"):
        entry_id = issue_id.removeprefix(f"{ISSUE_STALE_INBOUND_WEBHOOK}_")
        return N8nRotateWebhookRepairFlow(entry_id)
    return ConfirmRepairFlow()


class N8nRotateWebhookRepairFlow(RepairsFlow):
    """Mint a new inbound secret and revoke previous ones after auth failures."""

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Ask the user to confirm credential rotation."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Confirm and apply rotation (create new + revoke all others)."""
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is None:
                return self.async_abort(reason="entry_missing")
            await _async_rotate_and_reload(self.hass, entry)
            ir.async_delete_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_STALE_INBOUND_WEBHOOK}_{self._entry_id}",
            )
            return self.async_create_entry(title="", data={})

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        path = None
        if entry is not None and entry.data.get(CONF_WEBHOOK_ID):
            path = inbound_webhook_path(entry.data[CONF_WEBHOOK_ID])

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "entry_title": entry.title if entry else self._entry_id,
                "webhook_path": path or "unknown",
            },
        )


async def _async_rotate_and_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a new inbound secret, revoke others, notify once, reload."""
    data, record = rotate_secrets(
        dict(entry.data),
        label="repair-rotated",
        revoke_all_others=True,
    )
    hass.config_entries.async_update_entry(entry, data=data)
    reset_webhook_auth_failures(hass, entry.entry_id)
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    async_notify_new_inbound_secret(hass, entry, record, rotated=True)
    _LOGGER.info(
        "Repair rotated inbound webhook secrets for entry %s (new %s)",
        entry.entry_id,
        record["id"],
    )
    await hass.config_entries.async_reload(entry.entry_id)


def async_create_stale_webhook_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register a repairable issue for stale / failing inbound webhooks."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_STALE_INBOUND_WEBHOOK}_{entry.entry_id}",
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_STALE_INBOUND_WEBHOOK,
        translation_placeholders={
            "entry_title": entry.title or "n8n",
        },
    )


def async_delete_stale_webhook_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Clear a stale-webhook repair issue if present."""
    ir.async_delete_issue(
        hass, DOMAIN, f"{ISSUE_STALE_INBOUND_WEBHOOK}_{entry_id}"
    )
