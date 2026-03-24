"""Migration executor for twingate-idp-migrator.

Executes a MigrationPlan by calling resourceAccessAdd for each action,
logging every result to a ChangeLog, and emitting progress callbacks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from src.api.client import AccessInput, TwingateAPIError, TwingateClient
from src.core.changelog import append_entry, make_entry
from src.models import ChangeLog, MigrationAction, MigrationPlan
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Pause between mutations to respect API rate limits (seconds)
_MUTATION_PAUSE = 0.1

# Type alias for the progress callback
ProgressCallback = Callable[[int, int, MigrationAction, bool], None]

# Type alias for the cancellation check
CancelCheck = Callable[[], bool]


@dataclass
class ExecutionResult:
    """Summary of a completed migration execution."""

    total: int
    succeeded: int
    failed: int
    cancelled: bool = False


async def execute_plan(
    client: TwingateClient,
    plan: MigrationPlan,
    changelog: ChangeLog,
    on_progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    mutation_pause: float = _MUTATION_PAUSE,
) -> ExecutionResult:
    """Execute all actions in a MigrationPlan.

    For each action:
    - Calls client.add_resource_access with the action's settings.
    - Logs the result (success or failure) to the changelog.
    - Emits on_progress(current_index, total, action, success).
    - Sleeps mutation_pause seconds between calls.

    A single action failure never aborts the run — the executor continues
    and the caller sees the full result summary.

    Args:
        client: Authenticated Twingate API client.
        plan: The migration plan to execute.
        changelog: Changelog to append entries to (mutated in place).
        on_progress: Optional callback invoked after each action.
        cancel_check: Optional callable; if it returns True the loop breaks early.
        mutation_pause: Sleep duration (seconds) between mutations.

    Returns:
        ExecutionResult with total/succeeded/failed counts and cancelled flag.
    """
    total = len(plan.actions)
    succeeded = 0
    failed = 0
    cancelled = False

    for idx, action in enumerate(plan.actions):
        # Cooperative cancellation — check before each action
        if cancel_check is not None and cancel_check():
            cancelled = True
            logger.info("execution_cancelled", completed=idx, total=total)
            break

        success = False
        error_msg: str | None = None

        try:
            access_input = AccessInput(
                principal_id=action.to_group_id,
                security_policy_id=action.security_policy_id,
                expires_at=action.expires_at.isoformat() if action.expires_at else None,
                access_policy_mode=action.access_policy_mode,
                access_policy_duration_seconds=action.access_policy_duration_seconds,
            )
            api_ok = await client.add_resource_access(action.resource_id, [access_input])
            if api_ok:
                success = True
                succeeded += 1
                logger.info(
                    "action_succeeded",
                    resource_id=action.resource_id,
                    to_group_id=action.to_group_id,
                )
            else:
                error_msg = "API returned ok=false"
                failed += 1
                logger.warning(
                    "action_failed_ok_false",
                    resource_id=action.resource_id,
                    to_group_id=action.to_group_id,
                )
        except TwingateAPIError as exc:
            error_msg = str(exc)
            failed += 1
            logger.error(
                "action_failed_exception",
                resource_id=action.resource_id,
                to_group_id=action.to_group_id,
                error=error_msg,
            )

        append_entry(changelog, make_entry(action, success=success, error=error_msg))

        if on_progress is not None:
            on_progress(idx + 1, total, action, success)

        if idx < total - 1:
            await asyncio.sleep(mutation_pause)

    logger.info(
        "execution_complete",
        total=total,
        succeeded=succeeded,
        failed=failed,
        cancelled=cancelled,
    )
    return ExecutionResult(total=total, succeeded=succeeded, failed=failed, cancelled=cancelled)
