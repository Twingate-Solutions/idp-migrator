"""Group selector page — wizard step 2: assign groups to From and To sets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.models import GroupType, TwingateGroup
from src.ui.theme import semantic_color
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)

_GROUP_ROLE = Qt.ItemDataRole.UserRole


def _group_label(group: TwingateGroup) -> str:
    """Format a group for display in the list."""
    status = "" if group.is_active else " [inactive]"
    return f"{group.name} ({group.type.value}){status}"


class GroupSelectorPage(QWidget):
    """Wizard page 2: assign groups to the From and To migration sets."""

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the three-panel group selector UI."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Select From and To Groups")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Sort your groups into two buckets — this step does not create any pairings yet. "
            "On the next screen, the tool will automatically suggest which old group matches "
            "which new group based on name similarity."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        hint = QLabel(
            "Old IdP bucket: the groups being replaced (e.g. Okta). "
            "New IdP bucket: their replacements (e.g. Entra ID). "
            "Select multiple with Ctrl+Click or Shift+Click."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {semantic_color('text_muted')}; font-size: 12px;")
        outer.addWidget(hint)
        outer.addSpacing(12)

        self._synced_only_cb = QCheckBox(
            "Show SYNCED groups only (recommended — these are the IdP-managed groups)"
        )
        self._synced_only_cb.setChecked(True)
        self._synced_only_cb.toggled.connect(self._refresh_available)
        outer.addWidget(self._synced_only_cb)
        outer.addSpacing(8)

        panels = QHBoxLayout()
        outer.addLayout(panels, stretch=1)

        self._available_list = self._make_list_box("Available Groups", panels)
        panels.addLayout(self._make_button_column())
        self._from_list = self._make_list_box("Old IdP (From)", panels)
        panels.addSpacing(8)
        self._to_list = self._make_list_box("New IdP (To)", panels)

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

    def _make_list_box(self, title: str, parent: QHBoxLayout) -> QListWidget:
        """Create a labelled list widget and add it to the parent layout."""
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        lst = QListWidget()
        lst.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(lst)
        parent.addWidget(box, stretch=1)
        return lst

    def _make_button_column(self) -> QVBoxLayout:
        """Create the arrow button column between Available and From/To lists."""
        col = QVBoxLayout()
        col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        col.setSpacing(6)

        add_from = QPushButton("→ Old IdP")
        add_from.setMinimumWidth(80)
        add_from.setToolTip("Add selected to From set")
        add_from.clicked.connect(lambda: self._move_to(self._available_list, self._from_list))
        col.addWidget(add_from)

        add_to = QPushButton("→ New IdP")
        add_to.setMinimumWidth(80)
        add_to.setToolTip("Add selected to To set")
        add_to.clicked.connect(lambda: self._move_to(self._available_list, self._to_list))
        col.addWidget(add_to)

        col.addSpacing(12)

        remove = QPushButton("← Remove")
        remove.setMinimumWidth(100)
        remove.setToolTip("Return selected to Available")
        remove.clicked.connect(self._remove_selected)
        col.addWidget(remove)

        return col

    def on_shown(self) -> None:
        """Called by MainWindow when this page becomes visible."""
        self._demo_banner.setVisible(self._state.demo_mode)
        self._refresh_available()

    def _refresh_available(self) -> None:
        """Repopulate the Available list, excluding already-assigned groups."""
        synced_only = self._synced_only_cb.isChecked()
        assigned = (
            {self._from_list.item(i).data(_GROUP_ROLE).id for i in range(self._from_list.count())}
            | {self._to_list.item(i).data(_GROUP_ROLE).id for i in range(self._to_list.count())}
        )
        self._available_list.clear()
        for group in self._state.all_groups:
            if group.id in assigned:
                continue
            if synced_only and group.type != GroupType.SYNCED:
                continue
            item = QListWidgetItem(_group_label(group))
            item.setData(_GROUP_ROLE, group)
            self._available_list.addItem(item)

    def _move_to(self, source: QListWidget, target: QListWidget) -> None:
        """Move selected items from source list to target list."""
        for item in source.selectedItems():
            group: TwingateGroup = item.data(_GROUP_ROLE)
            new_item = QListWidgetItem(_group_label(group))
            new_item.setData(_GROUP_ROLE, group)
            target.addItem(new_item)
            source.takeItem(source.row(item))
        self._error_label.setText("")

    def _remove_selected(self) -> None:
        """Return selected items from From/To lists back to Available."""
        for lst in (self._from_list, self._to_list):
            for item in lst.selectedItems():
                group: TwingateGroup = item.data(_GROUP_ROLE)
                new_item = QListWidgetItem(_group_label(group))
                new_item.setData(_GROUP_ROLE, group)
                self._available_list.addItem(new_item)
                lst.takeItem(lst.row(item))
        self._error_label.setText("")

    def validate(self) -> bool:
        """Validate From/To sets, populate AppState, return True if valid."""
        from_groups = [
            self._from_list.item(i).data(_GROUP_ROLE) for i in range(self._from_list.count())
        ]
        to_groups = [
            self._to_list.item(i).data(_GROUP_ROLE) for i in range(self._to_list.count())
        ]

        if not from_groups:
            self._error_label.setText("Add at least one group to the From set.")
            return False
        if not to_groups:
            self._error_label.setText("Add at least one group to the To set.")
            return False
        if {g.id for g in from_groups} & {g.id for g in to_groups}:
            self._error_label.setText("A group cannot be in both From and To sets.")
            return False

        self._state.from_groups = from_groups
        self._state.to_groups = to_groups
        self._error_label.setText("")
        logger.info(
            "group_selector_validated",
            from_count=len(from_groups),
            to_count=len(to_groups),
        )
        return True
