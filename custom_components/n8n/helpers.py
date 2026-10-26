"""Pure helpers for options parsing and workflow filtering."""

from __future__ import annotations

from typing import Iterable

from .models import Workflow


def parse_csv_set(raw: str | None) -> set[str]:
    """Split a comma/newline/semicolon-separated string into a trimmed set."""
    if not raw:
        return set()
    tokens: set[str] = set()
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        value = part.strip()
        if value:
            tokens.add(value)
    return tokens


def workflow_is_exposed(
    workflow: Workflow,
    *,
    id_allowlist: set[str],
    id_blocklist: set[str],
    tag_allowlist: set[str],
    tag_blocklist: set[str],
) -> bool:
    """Return True when a workflow should become HA entities.

    Default (all allowlists empty): expose everything, then apply blocklists.
    When an allowlist is set, the workflow must match it. Id and tag allowlists
    are OR'd (match either). Blocklists always win.
    """
    if workflow.workflow_id in id_blocklist:
        return False
    if tag_blocklist and any(tag in tag_blocklist for tag in workflow.tags):
        return False

    has_id_allow = bool(id_allowlist)
    has_tag_allow = bool(tag_allowlist)
    if not has_id_allow and not has_tag_allow:
        return True

    id_ok = workflow.workflow_id in id_allowlist if has_id_allow else False
    tag_ok = (
        any(tag in tag_allowlist for tag in workflow.tags) if has_tag_allow else False
    )
    if has_id_allow and has_tag_allow:
        return id_ok or tag_ok
    if has_id_allow:
        return id_ok
    return tag_ok


def filter_workflows(
    workflows: Iterable[Workflow],
    *,
    id_allowlist: set[str],
    id_blocklist: set[str],
    tag_allowlist: set[str],
    tag_blocklist: set[str],
) -> list[Workflow]:
    """Filter workflows according to allow/block lists."""
    return [
        wf
        for wf in workflows
        if workflow_is_exposed(
            wf,
            id_allowlist=id_allowlist,
            id_blocklist=id_blocklist,
            tag_allowlist=tag_allowlist,
            tag_blocklist=tag_blocklist,
        )
    ]
