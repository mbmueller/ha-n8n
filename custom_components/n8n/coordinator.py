"""DataUpdateCoordinator for n8n workflows and executions."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import N8nApiClient, N8nApiError, N8nAuthError, is_failed_status
from .const import (
    CONF_EXECUTION_HISTORY_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_TAG_ALLOWLIST,
    CONF_TAG_BLOCKLIST,
    CONF_WORKFLOW_ALLOWLIST,
    CONF_WORKFLOW_BLOCKLIST,
    DEFAULT_EXECUTION_HISTORY_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_EXECUTION_HISTORY_LIMIT,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .helpers import filter_workflows, parse_csv_set
from .models import CoordinatorData, ExecutionSummary, Workflow

_LOGGER = logging.getLogger(__name__)


def _clamp_scan_interval(raw: Any) -> int:
    """Clamp poll interval to the supported range."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL
    return max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, value))


def _clamp_execution_limit(raw: Any) -> int:
    """Clamp execution history window size."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EXECUTION_HISTORY_LIMIT
    return max(1, min(MAX_EXECUTION_HISTORY_LIMIT, value))


class N8nDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Poll n8n for workflow metadata, webhook paths, and executions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: N8nApiClient,
    ) -> None:
        interval = _clamp_scan_interval(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )
        self.entry = entry
        self.client = client
        # Discovered webhook paths stay in coordinator memory only (never in
        # entity attributes as node graphs). None means "looked up, no webhook".
        self._webhook_path_cache: dict[str, str | None] = {}

    def apply_options(self) -> None:
        """Refresh poll interval from the current config entry options."""
        seconds = _clamp_scan_interval(
            self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        new_interval = timedelta(seconds=seconds)
        if self.update_interval != new_interval:
            self.update_interval = new_interval
            _LOGGER.debug(
                "n8n poll interval set to %ss for entry %s",
                seconds,
                self.entry.entry_id,
            )

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch workflows, enrich webhook paths, filter, and summarize executions."""
        self.apply_options()
        try:
            workflows = await self.client.async_get_workflows()
        except N8nAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except N8nApiError as err:
            raise UpdateFailed(str(err)) from err

        workflows = await self._async_enrich_webhook_paths(workflows)
        workflows = self._filter_workflows(workflows)

        last_executions: dict[str, ExecutionSummary] = {}
        failed_count = 0
        window = _clamp_execution_limit(
            self.entry.options.get(
                CONF_EXECUTION_HISTORY_LIMIT, DEFAULT_EXECUTION_HISTORY_LIMIT
            )
        )
        try:
            executions = await self.client.async_get_executions(limit=window)
        except N8nAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except N8nApiError as err:
            # Executions are best-effort; keep workflow entities usable.
            _LOGGER.warning(
                "Could not fetch n8n executions for entry %s: %s",
                self.entry.entry_id,
                err,
            )
            executions = []

        exposed_ids = {wf.workflow_id for wf in workflows}
        for summary in executions:
            if is_failed_status(summary.status):
                if (
                    summary.workflow_id is None
                    or summary.workflow_id in exposed_ids
                    or not exposed_ids
                ):
                    failed_count += 1
            if not summary.workflow_id:
                continue
            if exposed_ids and summary.workflow_id not in exposed_ids:
                continue
            # Executions are newest-first from the Public API.
            if summary.workflow_id not in last_executions:
                last_executions[summary.workflow_id] = summary

        return CoordinatorData(
            workflows=workflows,
            reachable=True,
            last_executions=last_executions,
            failed_execution_count=failed_count,
            execution_window_size=len(executions),
        )

    def _filter_workflows(self, workflows: list[Workflow]) -> list[Workflow]:
        """Apply allowlist / blocklist options (default = all)."""
        options = self.entry.options
        return filter_workflows(
            workflows,
            id_allowlist=parse_csv_set(options.get(CONF_WORKFLOW_ALLOWLIST)),
            id_blocklist=parse_csv_set(options.get(CONF_WORKFLOW_BLOCKLIST)),
            tag_allowlist=parse_csv_set(options.get(CONF_TAG_ALLOWLIST)),
            tag_blocklist=parse_csv_set(options.get(CONF_TAG_BLOCKLIST)),
        )

    async def _async_enrich_webhook_paths(
        self, workflows: list[Workflow]
    ) -> list[Workflow]:
        """Discover webhook paths from workflow JSON without retaining nodes.

        List responses often omit ``nodes``. Paths are cached in coordinator
        memory and copied onto Workflow.webhook_path for triggers/attributes.
        """
        enriched: list[Workflow] = []
        for workflow in workflows:
            path = workflow.webhook_path
            if path:
                self._webhook_path_cache[workflow.workflow_id] = path
                enriched.append(workflow)
                continue

            if workflow.workflow_id in self._webhook_path_cache:
                cached = self._webhook_path_cache[workflow.workflow_id]
                if cached:
                    workflow.webhook_path = cached
                enriched.append(workflow)
                continue

            try:
                detail = await self.client.async_get_workflow(workflow.workflow_id)
            except N8nApiError as err:
                _LOGGER.debug(
                    "Webhook discovery skipped for workflow %s: %s",
                    workflow.workflow_id,
                    err,
                )
                self._webhook_path_cache[workflow.workflow_id] = None
                enriched.append(workflow)
                continue

            discovered = detail.webhook_path
            self._webhook_path_cache[workflow.workflow_id] = discovered
            if discovered:
                workflow.webhook_path = discovered
                _LOGGER.debug(
                    "Discovered webhook path for workflow %s",
                    workflow.workflow_id,
                )
            enriched.append(workflow)

        # Drop cache entries for deleted workflows.
        live_ids = {wf.workflow_id for wf in workflows}
        stale = [wid for wid in self._webhook_path_cache if wid not in live_ids]
        for wid in stale:
            self._webhook_path_cache.pop(wid, None)

        return enriched

    def get_workflow(self, workflow_id: str) -> Any:
        """Return a cached workflow by id, or None."""
        if not self.data:
            return None
        return self.data.workflow_by_id(workflow_id)

    def get_last_execution(self, workflow_id: str) -> ExecutionSummary | None:
        """Return the last execution summary for a workflow, if known."""
        if not self.data:
            return None
        return self.data.last_execution(workflow_id)
