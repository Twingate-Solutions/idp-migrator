"""Execute page — wizard step 5: run the migration with progress reporting."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.changelog import new_changelog, save_changelog
from src.models import ChangeLog, MigrationAction
from src.ui.theme import semantic_color
from src.ui.workers import ExecuteWorker
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.core.executor import ExecutionResult
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)

_ICON_OK = "✓"
_ICON_FAIL = "✗"
_ICON_CANCEL = "⊘"


class ExecutePage(QWidget):
    """Wizard page 5: execute the migration plan with live progress."""

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._worker: ExecuteWorker | None = None
        self._changelog: ChangeLog | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the progress bar, action list, cancel button, and done button."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Running Migration")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "The migration is now running. Each action adds the new group's access to a resource, "
            "copying the same security policy and settings from the old group. "
            "A changelog is saved to ~/twingate_migration_logs/ when complete — "
            "keep it to enable rollback."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        self._status_label = QLabel("Preparing…")
        outer.addWidget(self._status_label)
        outer.addSpacing(8)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        outer.addWidget(self._progress)
        outer.addSpacing(8)

        self._action_list = QListWidget()
        self._action_list.setAlternatingRowColors(True)
        outer.addWidget(self._action_list, stretch=1)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        outer.addWidget(self._summary_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(120)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)

        self._done_btn = QPushButton("Close")
        self._done_btn.setFixedWidth(120)
        self._done_btn.setVisible(False)
        self._done_btn.clicked.connect(self._mw.close)
        btn_row.addWidget(self._done_btn)

        outer.addLayout(btn_row)

        self._demo_banner = QLabel(
            "Demo Mode \u2014 simulating execution. No real changes are being made."
        )
        self._demo_banner.setStyleSheet(
            f"color: {semantic_color('warning')}; font-weight: bold; padding: 4px 0;"
        )
        self._demo_banner.setVisible(False)
        outer.addWidget(self._demo_banner)

    def on_shown(self) -> None:
        """Start the migration worker when this page becomes visible."""
        # Clean up any previous worker
        if self._worker is not None:
            self._worker.finished.disconnect()
            self._worker.progress.disconnect()
            self._worker.error.disconnect()
            self._worker = None

        plan = self._state.plan
        client = self._state.client
        if plan is None or client is None:
            self._status_label.setText("Error: no plan or client available.")
            logger.error("execute_page_missing_plan_or_client")
            return

        self._demo_banner.setVisible(self._state.demo_mode)

        # Reset UI state
        self._action_list.clear()
        self._summary_label.setText("")
        self._progress.setValue(0)
        self._status_label.setText(f"Migrating {len(plan.actions)} access grant(s)…")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setVisible(True)
        self._done_btn.setVisible(False)

        # Disable navigation during execution
        self._mw.enable_back(False)
        self._mw.enable_next(False)

        self._changelog = new_changelog(self._state.tenant)
        self._worker = ExecuteWorker(
            client, plan, self._changelog, demo_mode=self._state.demo_mode, parent=self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        logger.info("execute_page_worker_started", actions=len(plan.actions))

    def _on_progress(
        self, current: int, total: int, action: MigrationAction, success: bool
    ) -> None:
        """Update progress bar and append action result to list."""
        pct = int(current / total * 100) if total else 0
        self._progress.setValue(pct)
        self._status_label.setText(f"Action {current} of {total}…")

        icon = _ICON_OK if success else _ICON_FAIL
        color = semantic_color("success") if success else semantic_color("error")
        text = (
            f"{icon}  {action.resource_name}  ←  {action.to_group_name}"
            f"  (from {action.from_group_name})"
        )
        item = QListWidgetItem(text)
        item.setForeground(QColor(color))
        self._action_list.addItem(item)
        self._action_list.scrollToBottom()

    def _on_finished(self, result: ExecutionResult) -> None:
        """Handle execution completion — show summary, save changelog, reveal Done button."""
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)

        if result.cancelled:
            self._progress.setValue(self._progress.value())
            self._status_label.setText("Migration cancelled.")
            item = QListWidgetItem(
                f"{_ICON_CANCEL}  Cancelled after {result.succeeded} action(s)."
            )
            item.setForeground(QColor(semantic_color("warning")))
            self._action_list.addItem(item)
        else:
            self._progress.setValue(100)
            self._status_label.setText("Migration complete.")

        parts = [f"{result.succeeded} succeeded", f"{result.failed} failed"]
        if result.cancelled:
            parts.append("cancelled early")
        self._summary_label.setText("  ·  ".join(parts))

        # Save changelog if any actions were executed
        if self._changelog is not None and self._changelog.entries:
            changelog = self._changelog
            now = datetime.datetime.now()
            changelog.completed_at = now
            ts = now.strftime("%Y%m%d_%H%M%S")
            path = Path.home() / "twingate_migration_logs" / f"changelog_{ts}.json"
            try:
                save_changelog(changelog, path)
                self._mw.set_status(f"Changelog saved to {path}")
            except Exception as exc:
                logger.error("changelog_save_failed", path=str(path), error=str(exc))
                self._mw.set_status(f"Warning: changelog not saved — {exc}")

        self._done_btn.setVisible(True)
        logger.info(
            "execute_page_finished",
            total=result.total,
            succeeded=result.succeeded,
            failed=result.failed,
            cancelled=result.cancelled,
        )

    def _on_error(self, message: str) -> None:
        """Handle a fatal worker error."""
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._status_label.setText(f"Error: {message}")
        item = QListWidgetItem(f"{_ICON_FAIL}  Fatal error: {message}")
        item.setForeground(QColor(semantic_color("error")))
        self._action_list.addItem(item)
        self._mw.set_status(f"Migration error: {message}")
        # Save any partial changelog entries for rollback purposes
        if self._changelog is not None and self._changelog.entries:
            now = datetime.datetime.now()
            self._changelog.completed_at = now
            ts = now.strftime("%Y%m%d_%H%M%S")
            path = Path.home() / "twingate_migration_logs" / f"changelog_{ts}.json"
            try:
                save_changelog(self._changelog, path)
                self._mw.set_status(f"Partial changelog saved to {path}")
            except Exception as save_exc:
                logger.error("changelog_save_failed", path=str(path), error=str(save_exc))
        self._done_btn.setVisible(True)
        logger.error("execute_page_worker_error", error=message)

    def _on_cancel(self) -> None:
        """Request cancellation of the running worker."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self._cancel_btn.setEnabled(False)
            self._status_label.setText(
                "Cancellation requested — finishing current action…"
            )
            logger.info("execute_page_cancel_requested")
