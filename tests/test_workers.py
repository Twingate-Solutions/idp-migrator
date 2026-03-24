"""Tests for QThread workers — tests inner async methods directly (no QApplication needed)."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.models import (
    ChangeLog,
    GroupType,
    MigrationAction,
    MigrationPlan,
    TwingateGroup,
    TwingateResource,
)
from src.ui.workers import ExecuteWorker, FetchResult, FetchWorker


def make_mock_client() -> MagicMock:
    """Build a mock TwingateClient with async fetch methods."""
    client = MagicMock()
    client.fetch_all_groups = AsyncMock(
        return_value=[TwingateGroup(id="g1", name="Okta-Eng", type=GroupType.SYNCED)]
    )
    client.fetch_all_resources_with_access = AsyncMock(
        return_value=[TwingateResource(id="r1", name="prod-db")]
    )
    client._close_http = AsyncMock(return_value=None)
    return client


def test_fetch_worker_inner_returns_result() -> None:
    """FetchWorker._fetch returns groups and resources from the client."""
    worker = FetchWorker.__new__(FetchWorker)
    worker._client = make_mock_client()

    result = asyncio.run(worker._fetch())

    assert isinstance(result, FetchResult)
    assert len(result.groups) == 1
    assert result.groups[0].name == "Okta-Eng"
    assert len(result.resources) == 1
    assert result.resources[0].name == "prod-db"


def test_fetch_worker_inner_calls_both_client_methods() -> None:
    """FetchWorker._fetch calls fetch_all_groups and fetch_all_resources_with_access."""
    mock_client = make_mock_client()
    worker = FetchWorker.__new__(FetchWorker)
    worker._client = mock_client

    asyncio.run(worker._fetch())

    mock_client.fetch_all_groups.assert_awaited_once()
    mock_client.fetch_all_resources_with_access.assert_awaited_once()


def make_action(resource_id: str = "r1") -> MigrationAction:
    """Build a minimal MigrationAction for testing."""
    return MigrationAction(
        resource_id=resource_id,
        resource_name=f"res-{resource_id}",
        from_group_id="fg1",
        from_group_name="old-group",
        to_group_id="tg1",
        to_group_name="new-group",
    )


def test_execute_worker_cancel_stops_early() -> None:
    """ExecuteWorker._execute_with_callback stops after request_cancel() is called."""
    actions = [make_action(f"r{i}") for i in range(5)]
    plan = MigrationPlan(actions=actions)
    changelog = ChangeLog(tenant="test", started_at=datetime.now())
    mock_client = MagicMock()
    mock_client.add_resource_access = AsyncMock(return_value=True)
    mock_client._close_http = AsyncMock(return_value=None)

    worker = ExecuteWorker.__new__(ExecuteWorker)
    worker._client = mock_client
    worker._plan = plan
    worker._changelog = changelog
    worker._demo_mode = False
    worker._cancel_event = threading.Event()

    call_count = 0

    def on_progress(current: int, total: int, action: MigrationAction, success: bool) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            worker.request_cancel()

    result = asyncio.run(worker._execute_with_callback(on_progress))

    assert result.cancelled is True
    assert result.succeeded == 1
    assert mock_client.add_resource_access.await_count == 1


def test_execute_worker_no_cancel_runs_all() -> None:
    """ExecuteWorker._execute_with_callback runs all actions when not cancelled."""
    actions = [make_action(f"r{i}") for i in range(3)]
    plan = MigrationPlan(actions=actions)
    changelog = ChangeLog(tenant="test", started_at=datetime.now())
    mock_client = MagicMock()
    mock_client.add_resource_access = AsyncMock(return_value=True)
    mock_client._close_http = AsyncMock(return_value=None)

    worker = ExecuteWorker.__new__(ExecuteWorker)
    worker._client = mock_client
    worker._plan = plan
    worker._changelog = changelog
    worker._demo_mode = False
    worker._cancel_event = threading.Event()

    result = asyncio.run(worker._execute_with_callback(None))

    assert result.cancelled is False
    assert result.succeeded == 3
    assert mock_client.add_resource_access.await_count == 3
