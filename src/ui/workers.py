"""QThread workers that bridge async Twingate API calls to the Qt main thread."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from src.api.client import TwingateAPIError, TwingateAuthError, TwingateClient
from src.core.executor import ExecutionResult, ProgressCallback, execute_plan
from src.core.rollback import RollbackProgressCallback, RollbackResult, RollbackScope, rollback
from src.models import (
    ChangeLog,
    ChangeLogEntry,
    MigrationAction,
    MigrationPlan,
    TwingateGroup,
    TwingateResource,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FetchResult:
    """Combined result of fetching groups and resources."""

    groups: list[TwingateGroup]
    resources: list[TwingateResource]


class ConnectWorker(QThread):
    """Tests API connectivity. Emits finished(bool) or error(str)."""

    finished = Signal(bool)
    error = Signal(str)

    def __init__(self, client: TwingateClient, parent: QObject | None = None) -> None:
        """Initialise with an authenticated client."""
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        """Run the connection check in a background thread."""
        try:
            ok = asyncio.run(self._connect())
            self.finished.emit(ok)
        except TwingateAuthError as exc:
            logger.warning("connect_worker_auth_error", error=str(exc))
            self.error.emit(f"Authentication failed: {exc}")
        except Exception as exc:
            logger.error("connect_worker_error", error=str(exc))
            self.error.emit(str(exc))

    async def _connect(self) -> bool:
        """Connect and clean up the HTTP client before returning."""
        try:
            return await self._client.connect()
        finally:
            await self._client._close_http()


class FetchWorker(QThread):
    """Fetches all groups and resources. Emits finished(FetchResult) or error(str)."""

    finished = Signal(FetchResult)
    error = Signal(str)

    def __init__(self, client: TwingateClient, parent: QObject | None = None) -> None:
        """Initialise with an authenticated client."""
        super().__init__(parent)
        self._client = client

    def run(self) -> None:
        """Fetch groups and resources in a background thread."""
        try:
            result = asyncio.run(self._fetch())
            self.finished.emit(result)
        except TwingateAPIError as exc:
            logger.error("fetch_worker_api_error", error=str(exc))
            self.error.emit(str(exc))
        except Exception as exc:
            logger.error("fetch_worker_error", error=str(exc))
            self.error.emit(str(exc))

    async def _fetch(self) -> FetchResult:
        """Inner async method — fetches groups and resources concurrently."""
        try:
            groups = await self._client.fetch_all_groups()
            resources = await self._client.fetch_all_resources_with_access()
            return FetchResult(groups=groups, resources=resources)
        finally:
            await self._client._close_http()


class ExecuteWorker(QThread):
    """Executes a MigrationPlan. Emits progress, finished(ExecutionResult), or error(str)."""

    progress = Signal(int, int, MigrationAction, bool)
    finished = Signal(ExecutionResult)
    error = Signal(str)

    def __init__(
        self,
        client: TwingateClient,
        plan: MigrationPlan,
        changelog: ChangeLog,
        demo_mode: bool = False,
        parent: QObject | None = None,
    ) -> None:
        """Initialise with client, plan, changelog, and optional demo flag."""
        super().__init__(parent)
        self._client = client
        self._plan = plan
        self._changelog = changelog
        self._demo_mode = demo_mode
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        """Signal the worker to stop after the current action completes."""
        self._cancel_event.set()
        logger.info("execute_worker_cancel_requested")

    def run(self) -> None:
        """Execute the migration plan in a background thread."""
        try:
            result = asyncio.run(self._execute())
            self.finished.emit(result)
        except Exception as exc:
            logger.error("execute_worker_error", error=str(exc))
            self.error.emit(str(exc))

    async def _execute(self) -> ExecutionResult:
        """Inner async method — executes the plan and emits per-action progress."""

        def on_progress(current: int, total: int, action: MigrationAction, success: bool) -> None:
            self.progress.emit(current, total, action, success)

        return await self._execute_with_callback(on_progress)

    async def _execute_with_callback(
        self,
        on_progress: ProgressCallback | None,
    ) -> ExecutionResult:
        """Test-accessible inner method that accepts an external progress callback."""
        try:
            if self._demo_mode:
                return await self._demo_execute(on_progress)
            return await execute_plan(
                client=self._client,
                plan=self._plan,
                changelog=self._changelog,
                on_progress=on_progress,
                cancel_check=self._cancel_event.is_set,
            )
        finally:
            await self._client._close_http()

    async def _demo_execute(self, on_progress: ProgressCallback | None) -> ExecutionResult:
        """Simulate migration execution with artificial delay — no real API calls."""
        import asyncio

        actions = self._plan.actions
        total = len(actions)
        succeeded = 0
        for i, action in enumerate(actions, 1):
            await asyncio.sleep(0.25)
            if self._cancel_event.is_set():
                return ExecutionResult(total=total, succeeded=succeeded, failed=0, cancelled=True)
            succeeded += 1
            if on_progress:
                on_progress(i, total, action, True)
        return ExecutionResult(total=total, succeeded=succeeded, failed=0, cancelled=False)


class RollbackWorker(QThread):
    """Executes a rollback. Emits progress, finished(RollbackResult), or error(str)."""

    progress = Signal(int, int, ChangeLogEntry, bool)
    finished = Signal(RollbackResult)
    error = Signal(str)

    def __init__(
        self,
        client: TwingateClient,
        changelog: ChangeLog,
        scope: RollbackScope,
        demo_mode: bool = False,
        parent: QObject | None = None,
    ) -> None:
        """Initialise with client, changelog, rollback scope, and optional demo flag."""
        super().__init__(parent)
        self._client = client
        self._changelog = changelog
        self._scope = scope
        self._demo_mode = demo_mode

    def run(self) -> None:
        """Execute the rollback in a background thread."""
        try:
            result = asyncio.run(self._rollback())
            self.finished.emit(result)
        except Exception as exc:
            logger.error("rollback_worker_error", error=str(exc))
            self.error.emit(str(exc))

    async def _rollback(self) -> RollbackResult:
        """Inner async method — executes rollback and emits per-entry progress."""

        def on_progress(current: int, total: int, entry: ChangeLogEntry, success: bool) -> None:
            self.progress.emit(current, total, entry, success)

        try:
            if self._demo_mode:
                return await self._demo_rollback(on_progress)
            return await rollback(
                client=self._client,
                changelog=self._changelog,
                scope=self._scope,
                on_progress=on_progress,
            )
        finally:
            await self._client._close_http()

    async def _demo_rollback(
        self,
        on_progress: RollbackProgressCallback | None,
    ) -> RollbackResult:
        """Simulate rollback with artificial delay — no real API calls."""
        import asyncio

        eligible = [e for e in self._changelog.entries if e.success]
        if self._scope.rollback_all:
            targets = eligible
        else:
            targets = [e for e in eligible if e.action.from_group_id == self._scope.from_group_id]
        total = len(targets)
        succeeded = 0
        for i, entry in enumerate(targets, 1):
            await asyncio.sleep(0.2)
            succeeded += 1
            if on_progress:
                on_progress(i, total, entry, True)
        return RollbackResult(total=total, succeeded=succeeded, failed=0)
