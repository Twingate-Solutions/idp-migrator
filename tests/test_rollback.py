"""Unit tests for src/core/rollback.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.api.client import TwingateAPIError
from src.core.rollback import RollbackResult, RollbackScope, rollback
from src.models import (
    AccessPolicyMode,
    ChangeLog,
    ChangeLogEntry,
    MigrationAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action(resource_id: str = "r1", from_group_id: str = "f1") -> MigrationAction:
    return MigrationAction(
        resource_id=resource_id,
        resource_name="prod-db",
        from_group_id=from_group_id,
        from_group_name="Okta-Eng",
        to_group_id="t1",
        to_group_name="Entra-Eng",
        access_policy_mode=AccessPolicyMode.MANUAL,
    )


def _entry(
    action: MigrationAction, success: bool = True, error: str | None = None
) -> ChangeLogEntry:
    return ChangeLogEntry(action=action, executed_at=datetime.now(), success=success, error=error)


def _changelog(*entries: ChangeLogEntry) -> ChangeLog:
    return ChangeLog(tenant="acme", started_at=datetime.now(), entries=list(entries))


def _mock_client(remove_returns: bool = True) -> AsyncMock:
    client = AsyncMock()
    client.remove_resource_access = AsyncMock(return_value=remove_returns)
    return client


# ---------------------------------------------------------------------------
# rollback — basic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_changelog_returns_zero_counts() -> None:
    client = _mock_client()
    cl = _changelog()
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result == RollbackResult(total=0, succeeded=0, failed=0)
    client.remove_resource_access.assert_not_called()


@pytest.mark.asyncio
async def test_single_successful_entry_rolled_back() -> None:
    client = _mock_client(remove_returns=True)
    cl = _changelog(_entry(_action("r1")))
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result == RollbackResult(total=1, succeeded=1, failed=0)
    client.remove_resource_access.assert_called_once_with("r1", ["t1"])


@pytest.mark.asyncio
async def test_failed_entries_are_skipped() -> None:
    """Only successful changelog entries are rolled back."""
    client = _mock_client()
    cl = _changelog(
        _entry(_action("r1"), success=True),
        _entry(_action("r2"), success=False),  # should be skipped
    )
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result.total == 1
    client.remove_resource_access.assert_called_once_with("r1", ["t1"])


@pytest.mark.asyncio
async def test_rollback_remove_api_failure_counted() -> None:
    """remove_resource_access returning False counts as failure."""
    client = _mock_client(remove_returns=False)
    cl = _changelog(_entry(_action()))
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result == RollbackResult(total=1, succeeded=0, failed=1)


@pytest.mark.asyncio
async def test_rollback_exception_counted_as_failure() -> None:
    client = AsyncMock()
    client.remove_resource_access = AsyncMock(side_effect=TwingateAPIError("boom"))
    cl = _changelog(_entry(_action()))
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result == RollbackResult(total=1, succeeded=0, failed=1)


@pytest.mark.asyncio
async def test_partial_failure_continues() -> None:
    """Failure on one rollback does not stop subsequent ones."""
    client = AsyncMock()
    client.remove_resource_access = AsyncMock(side_effect=[True, False, True])
    cl = _changelog(_entry(_action("r1")), _entry(_action("r2")), _entry(_action("r3")))
    result = await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert result == RollbackResult(total=3, succeeded=2, failed=1)


# ---------------------------------------------------------------------------
# rollback — reverse order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_processes_in_reverse_order() -> None:
    """Entries are rolled back most-recent first."""
    call_order: list[str] = []

    async def remove(resource_id: str, principal_ids: list[str]) -> bool:
        call_order.append(resource_id)
        return True

    client = AsyncMock()
    client.remove_resource_access = remove

    cl = _changelog(_entry(_action("r1")), _entry(_action("r2")), _entry(_action("r3")))
    await rollback(client, cl, RollbackScope(), mutation_pause=0)
    assert call_order == ["r3", "r2", "r1"]


# ---------------------------------------------------------------------------
# rollback — scope filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_all_includes_all_successful() -> None:
    client = _mock_client()
    cl = _changelog(
        _entry(_action("r1", from_group_id="f1")),
        _entry(_action("r2", from_group_id="f2")),
    )
    result = await rollback(client, cl, RollbackScope(rollback_all=True), mutation_pause=0)
    assert result.total == 2


@pytest.mark.asyncio
async def test_rollback_per_group_filters_by_from_group_id() -> None:
    """Per-group scope only rolls back entries for the specified from_group."""
    client = _mock_client()
    cl = _changelog(
        _entry(_action("r1", from_group_id="f1")),
        _entry(_action("r2", from_group_id="f2")),
        _entry(_action("r3", from_group_id="f1")),
    )
    result = await rollback(
        client,
        cl,
        RollbackScope(rollback_all=False, from_group_id="f1"),
        mutation_pause=0,
    )
    assert result.total == 2
    calls = [c[0][0] for c in client.remove_resource_access.call_args_list]
    assert set(calls) == {"r1", "r3"}


@pytest.mark.asyncio
async def test_rollback_per_group_without_from_group_id_raises() -> None:
    client = _mock_client()
    cl = _changelog(_entry(_action()))
    with pytest.raises(ValueError, match="from_group_id must be set"):
        await rollback(
            client, cl, RollbackScope(rollback_all=False, from_group_id=None), mutation_pause=0
        )


# ---------------------------------------------------------------------------
# rollback — progress callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_callback_called_per_entry() -> None:
    client = _mock_client()
    cl = _changelog(_entry(_action("r1")), _entry(_action("r2")))
    calls: list[tuple] = []

    def on_progress(idx: int, total: int, entry: ChangeLogEntry, success: bool) -> None:
        calls.append((idx, total, success))

    await rollback(client, cl, RollbackScope(), on_progress=on_progress, mutation_pause=0)
    assert calls == [(1, 2, True), (2, 2, True)]
