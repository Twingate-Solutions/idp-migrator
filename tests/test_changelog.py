"""Unit tests for src/core/changelog.py."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.core.changelog import (
    append_entry,
    load_changelog,
    make_entry,
    new_changelog,
    save_changelog,
)
from src.models import (
    AccessPolicyMode,
    MigrationAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action(resource_id: str = "r1") -> MigrationAction:
    return MigrationAction(
        resource_id=resource_id,
        resource_name="prod-db",
        from_group_id="f1",
        from_group_name="Okta-Eng",
        to_group_id="t1",
        to_group_name="Entra-Eng",
        access_policy_mode=AccessPolicyMode.MANUAL,
    )


# ---------------------------------------------------------------------------
# new_changelog
# ---------------------------------------------------------------------------

def test_new_changelog_empty_entries() -> None:
    cl = new_changelog("acme")
    assert cl.tenant == "acme"
    assert cl.entries == []
    assert cl.completed_at is None


def test_new_changelog_started_at_is_recent() -> None:
    before = datetime.now()
    cl = new_changelog("acme")
    after = datetime.now()
    assert before <= cl.started_at <= after


# ---------------------------------------------------------------------------
# append_entry
# ---------------------------------------------------------------------------

def test_append_entry_adds_to_list() -> None:
    cl = new_changelog("acme")
    entry = make_entry(_action(), success=True)
    append_entry(cl, entry)
    assert len(cl.entries) == 1
    assert cl.entries[0] is entry


def test_append_entry_multiple() -> None:
    cl = new_changelog("acme")
    append_entry(cl, make_entry(_action("r1"), success=True))
    append_entry(cl, make_entry(_action("r2"), success=False, error="fail"))
    assert len(cl.entries) == 2


# ---------------------------------------------------------------------------
# make_entry
# ---------------------------------------------------------------------------

def test_make_entry_success() -> None:
    action = _action()
    entry = make_entry(action, success=True)
    assert entry.action is action
    assert entry.success is True
    assert entry.error is None


def test_make_entry_failure_has_error() -> None:
    action = _action()
    entry = make_entry(action, success=False, error="Group not found")
    assert entry.success is False
    assert entry.error == "Group not found"


def test_make_entry_executed_at_recent() -> None:
    before = datetime.now()
    entry = make_entry(_action(), success=True)
    after = datetime.now()
    assert before <= entry.executed_at <= after


# ---------------------------------------------------------------------------
# save_changelog / load_changelog
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    cl = new_changelog("acme")
    append_entry(cl, make_entry(_action("r1"), success=True))
    append_entry(cl, make_entry(_action("r2"), success=False, error="oops"))

    path = tmp_path / "changelog.json"
    save_changelog(cl, path)

    loaded = load_changelog(path)
    assert loaded.tenant == "acme"
    assert len(loaded.entries) == 2
    assert loaded.entries[0].action.resource_id == "r1"
    assert loaded.entries[0].success is True
    assert loaded.entries[1].action.resource_id == "r2"
    assert loaded.entries[1].error == "oops"


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "changelog.json"
    save_changelog(new_changelog("acme"), path)
    assert path.exists()


def test_save_produces_valid_json(tmp_path: Path) -> None:
    cl = new_changelog("acme")
    path = tmp_path / "changelog.json"
    save_changelog(cl, path)
    data = json.loads(path.read_text())
    assert data["tenant"] == "acme"


def test_load_nonexistent_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_changelog(tmp_path / "missing.json")


def test_load_invalid_json_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse changelog"):
        load_changelog(path)


def test_load_wrong_schema_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text('{"foo": "bar"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse changelog"):
        load_changelog(path)
