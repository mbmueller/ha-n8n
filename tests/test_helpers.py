"""Tests for workflow filtering helpers."""

from __future__ import annotations

from custom_components.n8n.helpers import filter_workflows, parse_csv_set, workflow_is_exposed
from custom_components.n8n.models import Workflow


def _wf(wid: str, *tags: str) -> Workflow:
    return Workflow(workflow_id=wid, name=wid, active=True, tags=list(tags))


def test_parse_csv_set() -> None:
    assert parse_csv_set("a, b;c\nd") == {"a", "b", "c", "d"}
    assert parse_csv_set("") == set()
    assert parse_csv_set(None) == set()


def test_default_exposes_all() -> None:
    assert workflow_is_exposed(
        _wf("1", "home"),
        id_allowlist=set(),
        id_blocklist=set(),
        tag_allowlist=set(),
        tag_blocklist=set(),
    )


def test_id_allowlist() -> None:
    assert workflow_is_exposed(
        _wf("1"),
        id_allowlist={"1"},
        id_blocklist=set(),
        tag_allowlist=set(),
        tag_blocklist=set(),
    )
    assert not workflow_is_exposed(
        _wf("2"),
        id_allowlist={"1"},
        id_blocklist=set(),
        tag_allowlist=set(),
        tag_blocklist=set(),
    )


def test_tag_allowlist_ha_exposed() -> None:
    assert workflow_is_exposed(
        _wf("1", "ha-exposed"),
        id_allowlist=set(),
        id_blocklist=set(),
        tag_allowlist={"ha-exposed"},
        tag_blocklist=set(),
    )
    assert not workflow_is_exposed(
        _wf("2", "internal"),
        id_allowlist=set(),
        id_blocklist=set(),
        tag_allowlist={"ha-exposed"},
        tag_blocklist=set(),
    )


def test_blocklist_wins() -> None:
    assert not workflow_is_exposed(
        _wf("1", "ha-exposed"),
        id_allowlist={"1"},
        id_blocklist={"1"},
        tag_allowlist=set(),
        tag_blocklist=set(),
    )


def test_filter_workflows_or_allowlists() -> None:
    workflows = [_wf("1", "a"), _wf("2", "b"), _wf("3", "c")]
    filtered = filter_workflows(
        workflows,
        id_allowlist={"1"},
        id_blocklist=set(),
        tag_allowlist={"b"},
        tag_blocklist=set(),
    )
    assert {w.workflow_id for w in filtered} == {"1", "2"}
