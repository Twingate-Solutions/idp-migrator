"""Dry run page — wizard step 4: preview all planned changes before execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.planner import build_plan
from src.models import MigrationAction
from src.ui.theme import semantic_color
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)


class DryRunPage(QWidget):
    """Wizard page 4: preview all planned access changes before executing."""

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the preview tree and summary bar."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Preview Migration Changes")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "This is a read-only preview — no changes have been made to your Twingate account. "
            "Review every planned access grant before proceeding. "
            "Expand a mapping to see each affected resource along with the security policy "
            "and access mode that will be copied to the new group."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(4)

        hint = QLabel(
            "Click 'Run Migration \u2192' only when you are satisfied with the plan. "
            "A changelog file will be saved after execution so you can roll back if needed."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {semantic_color('text_muted')}; font-size: 12px;")
        outer.addWidget(hint)
        outer.addSpacing(8)

        bar = QHBoxLayout()
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-weight: bold;")
        bar.addWidget(self._summary_label)
        bar.addStretch()

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Item", "Detail"])
        self._tree.setColumnWidth(0, 380)
        self._tree.setAlternatingRowColors(True)

        expand_btn = QPushButton("Expand All")
        expand_btn.setFixedWidth(100)
        expand_btn.clicked.connect(self._tree.expandAll)
        collapse_btn = QPushButton("Collapse All")
        collapse_btn.setFixedWidth(100)
        collapse_btn.clicked.connect(self._tree.collapseAll)
        bar.addWidget(expand_btn)
        bar.addWidget(collapse_btn)

        outer.addLayout(bar)
        outer.addWidget(self._tree, stretch=1)

        self._demo_banner = QLabel(
            "Demo Mode \u2014 using sample Okta \u2192 Entra ID data. "
            "No real Twingate account is connected."
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
        """Build the migration plan and populate the preview tree."""
        self._demo_banner.setVisible(self._state.demo_mode)
        self._mw.enable_next(False)
        self._error_label.setText("")
        self._tree.clear()

        plan = build_plan(self._state.mappings, self._state.resources)
        self._state.plan = plan

        if not plan.actions:
            self._summary_label.setText(
                "No changes needed — all target groups already have access."
            )
            self._mw.enable_next(False)
            logger.info("dry_run_page_no_actions")
            return

        # Group actions by (from_group_name, to_group_name) mapping pair
        mapping_buckets: dict[tuple[str, str], list[MigrationAction]] = {}
        for action in plan.actions:
            key = (action.from_group_name, action.to_group_name)
            mapping_buckets.setdefault(key, []).append(action)

        for (from_name, to_name), actions in mapping_buckets.items():
            mapping_item = QTreeWidgetItem(self._tree)
            mapping_item.setText(0, f"{from_name}  →  {to_name}")
            mapping_item.setText(1, f"{len(actions)} resource(s)")
            mapping_item.setExpanded(True)
            font = mapping_item.font(0)
            font.setBold(True)
            mapping_item.setFont(0, font)

            for action in actions:
                res_item = QTreeWidgetItem(mapping_item)
                res_item.setText(0, f"  {action.resource_name}")
                res_item.setText(1, action.resource_id)
                res_item.setExpanded(True)

                access_mode = (
                    str(action.access_policy_mode)
                    if action.access_policy_mode
                    else "None"
                )
                for label, value in [
                    ("Security Policy", action.security_policy_name or "None"),
                    ("Access Mode", access_mode),
                    ("Expires", action.expires_at.isoformat() if action.expires_at else "Never"),
                ]:
                    child = QTreeWidgetItem(res_item)
                    child.setText(0, f"    {label}")
                    child.setText(1, value)

        unique_resources = len({a.resource_id for a in plan.actions})
        self._summary_label.setText(
            f"{len(mapping_buckets)} mapping(s) · "
            f"{unique_resources} resource(s) · "
            f"{len(plan.actions)} access grant(s) to add"
        )
        self._mw.enable_next(True)
        logger.info(
            "dry_run_page_loaded",
            mappings=len(mapping_buckets),
            resources=unique_resources,
            actions=len(plan.actions),
        )

    def validate(self) -> bool:
        """Validate that a non-empty plan exists before advancing to execution."""
        if self._state.plan is None or not self._state.plan.actions:
            self._error_label.setText(
                "No changes planned. Go back and ensure at least one confirmed mapping "
                "has resources to migrate."
            )
            return False
        self._error_label.setText("")
        return True
