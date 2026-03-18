"""Unit tests for src/core/executor.py."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.api.client import TwingateAPIError
from src.core.changelog import new_changelog
from src.core.executor import ExecutionResult, execute_plan
from src.models import (
    AccessPolicyMode,
    MigrationAction,
    MigrationPlan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action(resource_id: str = "r1", to_group_id: str = "t1") -> MigrationAction:
    return MigrationAction(
        resource_id=resource_id,
        resource_name="prod-db",
        from_group_id="f1",
        from_group_name="Okta-Eng",
        to_group_id=to_group_id,
        to_group_name="Entra-Eng",
        access_policy_mode=AccessPolicyMode.MANUAL,
    )


def _plan(*actions: MigrationAction) -> MigrationPlan:
    return MigrationPlan(actions=list(actions))


def _mock_client(add_returns: bool = True) -> AsyncMock:
    client = AsyncMock()
    client.add_resource_access = AsyncMock(return_value=add_returns)
    return client


# ---------------------------------------------------------------------------
# execute_plan — basic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_plan_returns_zero_counts() -> None:
    client = _mock_client()
    cl = new_changelog("acme")
    result = await execute_plan(client, _plan(), cl, mutation_pause=0)
    assert result == ExecutionResult(total=0, succeeded=0, failed=0)
    client.add_resource_access.assert_not_called()


@pytest.mark.asyncio
async def test_single_success_action() -> None:
    client = _mock_client(add_returns=True)
    cl = new_changelog("acme")
    result = await execute_plan(client, _plan(_action()), cl, mutation_pause=0)
    assert result == ExecutionResult(total=1, succeeded=1, failed=0)


@pytest.mark.asyncio
async def test_single_failure_action_ok_false() -> None:
    """API returning ok=False counts as a failure but does not raise."""
    client = _mock_client(add_returns=False)
    cl = new_changelog("acme")
    result = await execute_plan(client, _plan(_action()), cl, mutation_pause=0)
    assert result == ExecutionResult(total=1, succeeded=0, failed=1)


@pytest.mark.asyncio
async def test_exception_counts_as_failure() -> None:
    """TwingateAPIError from client is caught and counted as failure."""
    client = AsyncMock()
    client.add_resource_access = AsyncMock(side_effect=TwingateAPIError("boom"))
    cl = new_changelog("acme")
    result = await execute_plan(client, _plan(_action()), cl, mutation_pause=0)
    assert result == ExecutionResult(total=1, succeeded=0, failed=1)


@pytest.mark.asyncio
async def test_partial_failure_continues() -> None:
    """Failure on one action does not stop subsequent actions."""
    client = AsyncMock()
    client.add_resource_access = AsyncMock(side_effect=[True, False, True])
    cl = new_changelog("acme")
    plan = _plan(_action("r1"), _action("r2"), _action("r3"))
    result = await execute_plan(client, plan, cl, mutation_pause=0)
    assert result == ExecutionResult(total=3, succeeded=2, failed=1)
    assert client.add_resource_access.call_count == 3


# ---------------------------------------------------------------------------
# execute_plan — changelog entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_action_logged_to_changelog() -> None:
    client = _mock_client(add_returns=True)
    cl = new_changelog("acme")
    await execute_plan(client, _plan(_action("r1")), cl, mutation_pause=0)
    assert len(cl.entries) == 1
    assert cl.entries[0].success is True
    assert cl.entries[0].action.resource_id == "r1"
    assert cl.entries[0].error is None


@pytest.mark.asyncio
async def test_failed_action_logged_with_error() -> None:
    client = _mock_client(add_returns=False)
    cl = new_changelog("acme")
    await execute_plan(client, _plan(_action("r1")), cl, mutation_pause=0)
    assert cl.entries[0].success is False
    assert cl.entries[0].error is not None


@pytest.mark.asyncio
async def test_all_actions_logged() -> None:
    client = AsyncMock()
    client.add_resource_access = AsyncMock(side_effect=[True, False])
    cl = new_changelog("acme")
    plan = _plan(_action("r1"), _action("r2"))
    await execute_plan(client, plan, cl, mutation_pause=0)
    assert len(cl.entries) == 2


# ---------------------------------------------------------------------------
# execute_plan — progress callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_callback_called_per_action() -> None:
    client = _mock_client(add_returns=True)
    cl = new_changelog("acme")
    calls: list[tuple] = []

    def on_progress(idx: int, total: int, action: MigrationAction, success: bool) -> None:
        calls.append((idx, total, success))

    plan = _plan(_action("r1"), _action("r2"))
    await execute_plan(client, plan, cl, on_progress=on_progress, mutation_pause=0)
    assert calls == [(1, 2, True), (2, 2, True)]


@pytest.mark.asyncio
async def test_no_progress_callback_is_fine() -> None:
    """on_progress=None does not raise."""
    client = _mock_client()
    cl = new_changelog("acme")
    result = await execute_plan(client, _plan(_action()), cl, on_progress=None, mutation_pause=0)
    assert result.total == 1


# ---------------------------------------------------------------------------
# execute_plan — AccessInput construction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_access_input_built_from_action_fields() -> None:
    """The client is called with the correct access input derived from the action."""
    client = _mock_client()
    cl = new_changelog("acme")
    action = MigrationAction(
        resource_id="r1",
        resource_name="prod-db",
        from_group_id="f1",
        from_group_name="Okta-Eng",
        to_group_id="t1",
        to_group_name="Entra-Eng",
        security_policy_id="pol-1",
        access_policy_mode=AccessPolicyMode.AUTO_LOCK,
    )
    await execute_plan(client, _plan(action), cl, mutation_pause=0)

    client.add_resource_access.assert_called_once()
    call_args = client.add_resource_access.call_args
    resource_id_arg = call_args[0][0]
    access_list = call_args[0][1]

    assert resource_id_arg == "r1"
    assert len(access_list) == 1
    access_input = access_list[0]
    assert access_input.principal_id == "t1"
    assert access_input.security_policy_id == "pol-1"
    assert access_input.access_policy_mode == AccessPolicyMode.AUTO_LOCK
