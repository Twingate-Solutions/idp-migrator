"""Rollback engine for twingate-idp-migrator.

Reverses successful resourceAccessAdd mutations by calling
resourceAccessRemove, using the changelog as the source of truth.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from src.api.client import TwingateAPIError, TwingateClient
from src.models import ChangeLog, ChangeLogEntry
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Type alias for the rollback progress callback
RollbackProgressCallback = Callable[[int, int, ChangeLogEntry, bool], None]


@dataclass
class RollbackScope:
    """Defines which changelog entries to roll back.

    Attributes:
        rollback_all: If True, roll back all successful entries.
        from_group_id: If rollback_all=False, only roll back entries
            where action.from_group_id matches this value.
    """

    rollback_all: bool = True
    from_group_id: str | None = None


@dataclass
class RollbackResult:
    """Summary of a completed rollback operation."""

    total: int
    succeeded: int
    failed: int


async def rollback(
    client: TwingateClient,
    changelog: ChangeLog,
    scope: RollbackScope,
    on_progress: RollbackProgressCallback | None = None,
    mutation_pause: float = 0.1,
) -> RollbackResult:
    """Reverse successful migration actions from a changelog.

    Filters the changelog to successful entries matching the scope,
    then calls resourceAccessRemove in reverse order (last-in, first-out).

    Args:
        client: Authenticated Twingate API client.
        changelog: Previously saved migration changelog.
        scope: Which entries to roll back (all or per-group).
        on_progress: Optional callback: (current, total, entry, success).
        mutation_pause: Sleep between mutations (seconds).

    Returns:
        RollbackResult with total/succeeded/failed counts.
    """
    # Filter to successful entries only
    candidates = [e for e in changelog.entries if e.success]

    # Apply scope filter
    if not scope.rollback_all:
        if scope.from_group_id is None:
            raise ValueError("from_group_id must be set when rollback_all=False")
        candidates = [
            e for e in candidates if e.action.from_group_id == scope.from_group_id
        ]

    # Reverse order: undo most-recent mutations first
    to_rollback = list(reversed(candidates))
    total = len(to_rollback)
    succeeded = 0
    failed = 0

    for idx, entry in enumerate(to_rollback):
        success = False
        try:
            api_ok = await client.remove_resource_access(
                entry.action.resource_id,
                [entry.action.to_group_id],
            )
            if api_ok:
                success = True
                succeeded += 1
                logger.info(
                    "rollback_action_succeeded",
                    resource_id=entry.action.resource_id,
                    to_group_id=entry.action.to_group_id,
                )
            else:
                failed += 1
                logger.warning(
                    "rollback_action_failed_ok_false",
                    resource_id=entry.action.resource_id,
                    to_group_id=entry.action.to_group_id,
                )
        except TwingateAPIError as exc:
            failed += 1
            logger.error(
                "rollback_action_failed_exception",
                resource_id=entry.action.resource_id,
                to_group_id=entry.action.to_group_id,
                error=str(exc),
            )

        if on_progress is not None:
            on_progress(idx + 1, total, entry, success)

        if idx < total - 1:
            await asyncio.sleep(mutation_pause)

    logger.info(
        "rollback_complete",
        total=total,
        succeeded=succeeded,
        failed=failed,
    )
    return RollbackResult(total=total, succeeded=succeeded, failed=failed)
