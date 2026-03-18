"""Rollback page — load a migration changelog and undo executed changes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.core.changelog import load_changelog
from src.core.rollback import RollbackScope
from src.models import ChangeLog
from src.ui.theme import semantic_color
from src.ui.workers import RollbackWorker
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.core.rollback import RollbackResult
    from src.models import ChangeLogEntry
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)

_ICON_OK = "✓"
_ICON_FAIL = "✗"


class RollbackPage(QWidget):
    """Rollback page: load a changelog, configure scope, and execute rollback."""

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._changelog: ChangeLog | None = None
        self._worker: RollbackWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the changelog loader, scope selector, and progress area."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Rollback Migration")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Load a changelog file from a previous migration to undo the changes it made. "
            "Changelog files are saved to ~/twingate_migration_logs/ after each execution.\n"
            "Rollback removes the new groups' access to resources — it does not restore anything "
            "that existed before the migration. Choose 'Roll back all' to undo everything, "
            "or select a specific From Group to roll back only that group's changes."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(12)

        self._no_client_label = QLabel(
            "⚠ No active connection. Please connect to your Twingate tenant first "
            "(Step 1) before using rollback."
        )
        self._no_client_label.setStyleSheet(f"color: {semantic_color('warning')}; padding: 12px;")
        self._no_client_label.setWordWrap(True)
        outer.addWidget(self._no_client_label)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._content)

        # File picker
        file_row = QHBoxLayout()
        self._file_label = QLabel("No changelog loaded.")
        self._file_label.setWordWrap(True)
        file_row.addWidget(self._file_label, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._browse_changelog)
        file_row.addWidget(browse_btn)
        content_layout.addLayout(file_row)
        content_layout.addSpacing(4)

        self._changelog_summary = QLabel("")
        content_layout.addWidget(self._changelog_summary)
        content_layout.addSpacing(8)

        # Scope selector
        scope_label = QLabel("Rollback scope:")
        scope_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(scope_label)

        self._radio_all = QRadioButton("Roll back all successful actions")
        self._radio_all.setChecked(True)
        self._radio_group = QRadioButton("Roll back specific From Group:")
        self._btn_group = QButtonGroup(self)
        self._btn_group.addButton(self._radio_all)
        self._btn_group.addButton(self._radio_group)
        content_layout.addWidget(self._radio_all)

        group_row = QHBoxLayout()
        group_row.addWidget(self._radio_group)
        self._group_combo = QComboBox()
        self._group_combo.setMinimumWidth(200)
        self._group_combo.setEnabled(False)
        group_row.addWidget(self._group_combo)
        group_row.addStretch()
        content_layout.addLayout(group_row)
        self._radio_group.toggled.connect(
            lambda checked: self._group_combo.setEnabled(checked)
        )
        content_layout.addSpacing(8)

        self._execute_btn = QPushButton("Execute Rollback")
        self._execute_btn.setFixedWidth(160)
        self._execute_btn.setEnabled(False)
        self._execute_btn.clicked.connect(self._start_rollback)
        content_layout.addWidget(self._execute_btn)
        content_layout.addSpacing(8)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        content_layout.addWidget(self._progress)

        self._result_list = QListWidget()
        self._result_list.setAlternatingRowColors(True)
        self._result_list.setVisible(False)
        content_layout.addWidget(self._result_list, stretch=1)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(self._summary_label)

        self._demo_banner = QLabel(
            "Demo Mode \u2014 simulating rollback. No real changes are being made."
        )
        self._demo_banner.setStyleSheet(
            f"color: {semantic_color('warning')}; font-weight: bold; padding: 4px 0;"
        )
        self._demo_banner.setVisible(False)
        outer.addWidget(self._demo_banner)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"color: {semantic_color('error')};")
        outer.addWidget(self._error_label)

    def on_shown(self) -> None:
        """Update visibility based on whether a client connection is active."""
        self._demo_banner.setVisible(self._state.demo_mode)
        has_client = self._state.client is not None
        self._no_client_label.setVisible(not has_client and not self._state.demo_mode)
        self._content.setVisible(has_client)
        self._mw.enable_next(False)
        self._error_label.setText("")

    def _browse_changelog(self) -> None:
        """Open a file dialog and load the selected changelog JSON."""
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Migration Changelog",
            str(Path.home()),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            self._changelog = load_changelog(path)
        except (FileNotFoundError, ValueError) as exc:
            self._error_label.setText(f"Could not load changelog: {exc}")
            self._execute_btn.setEnabled(False)
            return

        self._error_label.setText("")
        self._file_label.setText(str(path))
        successful = [e for e in self._changelog.entries if e.success]
        self._changelog_summary.setText(
            f"Tenant: {self._changelog.tenant}  ·  "
            f"Started: {self._changelog.started_at.strftime('%Y-%m-%d %H:%M:%S')}  ·  "
            f"{len(successful)} successful action(s) eligible for rollback"
        )

        from_groups: dict[str, str] = {}
        for entry in successful:
            from_groups[entry.action.from_group_id] = entry.action.from_group_name
        self._group_combo.clear()
        for gid, gname in from_groups.items():
            self._group_combo.addItem(gname, userData=gid)

        self._execute_btn.setEnabled(bool(successful))
        self._result_list.clear()
        self._result_list.setVisible(False)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._summary_label.setText("")
        logger.info(
            "rollback_page_changelog_loaded",
            path=str(path),
            entries=len(self._changelog.entries),
            eligible=len(successful),
        )

    def _start_rollback(self) -> None:
        """Validate and launch the RollbackWorker."""
        # Prevent double-run while a rollback is already in progress
        if self._worker is not None and self._worker.isRunning():
            return

        if self._changelog is None or self._state.client is None:
            self._error_label.setText("No changelog or client available.")
            return

        if self._radio_all.isChecked():
            scope = RollbackScope(rollback_all=True)
        else:
            gid = self._group_combo.currentData()
            if not gid:
                self._error_label.setText("Select a From Group to roll back.")
                return
            scope = RollbackScope(rollback_all=False, from_group_id=gid)

        self._execute_btn.setEnabled(False)
        self._result_list.clear()
        self._result_list.setVisible(True)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._summary_label.setText("")
        self._error_label.setText("")

        # Disconnect any previous worker to prevent stale signal delivery
        if self._worker is not None:
            self._worker.progress.disconnect()
            self._worker.finished.disconnect()
            self._worker.error.disconnect()
            self._worker = None

        self._worker = RollbackWorker(
            self._state.client, self._changelog, scope,
            demo_mode=self._state.demo_mode, parent=self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        logger.info("rollback_page_worker_started")

    def _on_progress(
        self, current: int, total: int, entry: ChangeLogEntry, success: bool
    ) -> None:
        """Update progress bar and append rollback result."""
        pct = int(current / total * 100) if total else 0
        self._progress.setValue(pct)
        icon = _ICON_OK if success else _ICON_FAIL
        color = semantic_color("success") if success else semantic_color("error")
        text = (
            f"{icon}  Removed {entry.action.to_group_name} from "
            f"{entry.action.resource_name}"
        )
        item = QListWidgetItem(text)
        item.setForeground(QColor(color))
        self._result_list.addItem(item)
        self._result_list.scrollToBottom()

    def _on_finished(self, result: RollbackResult) -> None:
        """Handle rollback completion."""
        self._progress.setValue(100)
        self._summary_label.setText(
            f"Rollback complete — {result.succeeded} succeeded · {result.failed} failed"
        )
        self._mw.set_status(
            f"Rollback done: {result.succeeded} removed, {result.failed} failed."
        )
        self._execute_btn.setEnabled(True)
        logger.info(
            "rollback_page_finished",
            total=result.total,
            succeeded=result.succeeded,
            failed=result.failed,
        )

    def _on_error(self, message: str) -> None:
        """Handle a fatal rollback worker error."""
        self._error_label.setText(f"Rollback error: {message}")
        self._execute_btn.setEnabled(True)
        logger.error("rollback_page_worker_error", error=message)
