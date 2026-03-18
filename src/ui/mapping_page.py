"""Mapping review page — wizard step 3: review and adjust fuzzy-matched group pairs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.core.matcher import match_groups
from src.models import GroupMapping, TwingateGroup
from src.ui.delegates import CheckBoxDelegate, ComboBoxDelegate
from src.ui.theme import semantic_color
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)

COL_FROM = 0
COL_TO = 1
COL_CONFIDENCE = 2
COL_STATUS = 3
COL_CONFIRMED = 4

HEADERS = ["From Group", "To Group", "Confidence", "Status", "Confirmed"]
_UNMAPPED = "(Unmapped)"
_HIGH, _MED = 0.80, 0.50


def _conf_color(confidence: float) -> QColor:
    """Return a traffic-light colour based on match confidence."""
    if confidence >= _HIGH:
        return QColor(semantic_color("success"))
    if confidence >= _MED:
        return QColor(semantic_color("warning"))
    return QColor(semantic_color("error"))


def _status_text(mapping: GroupMapping) -> str:
    """Return a short status string for a mapping row."""
    if mapping.to_group is None:
        return "✗ Unmapped"
    return "✓ High" if mapping.confidence >= _HIGH else "⚠ Low"


class MappingTableModel(QAbstractTableModel):
    """Qt data model for the fuzzy-match review table.

    Columns: From Group | To Group (editable via combo) | Confidence | Status | Confirmed
    """

    def __init__(
        self, mappings: list[GroupMapping], to_groups: list[TwingateGroup]
    ) -> None:
        """Initialise with the initial mapping list and available To groups."""
        super().__init__()
        self._mappings = list(mappings)
        self._to_groups = to_groups
        self._to_by_name: dict[str, TwingateGroup] = {g.name: g for g in to_groups}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        """Return number of mapping rows."""
        return len(self._mappings)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        """Return number of columns."""
        return len(HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Return column header labels."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Return cell data for display, foreground colour, and checkbox state."""
        if not index.isValid():
            return None
        mapping = self._mappings[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_FROM:
                return mapping.from_group.name
            if col == COL_TO:
                return mapping.to_group.name if mapping.to_group else _UNMAPPED
            if col == COL_CONFIDENCE:
                return f"{mapping.confidence * 100:.0f}%" if mapping.to_group else "—"
            if col == COL_STATUS:
                return _status_text(mapping)
            if col == COL_CONFIRMED:
                return "Yes" if mapping.is_confirmed else "No"

        if role == Qt.ItemDataRole.ForegroundRole:
            if col in (COL_CONFIDENCE, COL_STATUS) and mapping.to_group is not None:
                return QBrush(_conf_color(mapping.confidence))
            if col == COL_STATUS and mapping.to_group is None:
                return QBrush(QColor(semantic_color("error")))

        if role == Qt.ItemDataRole.CheckStateRole and col == COL_CONFIRMED:
            return Qt.CheckState.Checked if mapping.is_confirmed else Qt.CheckState.Unchecked

        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Handle To Group combo edits and Confirmed checkbox toggles."""
        if not index.isValid():
            return False
        mapping = self._mappings[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.EditRole and col == COL_TO:
            name = str(value)
            if name == _UNMAPPED:
                mapping.to_group = None
                mapping.confidence = 0.0
                mapping.is_confirmed = False
            else:
                group = self._to_by_name.get(name)
                if group is None:
                    return False
                mapping.to_group = group
                mapping.is_confirmed = True
            self.dataChanged.emit(
                self.index(index.row(), 0),
                self.index(index.row(), len(HEADERS) - 1),
            )
            return True

        if (
            role == Qt.ItemDataRole.CheckStateRole
            and col == COL_CONFIRMED
            and mapping.to_group is not None
        ):
            mapping.is_confirmed = value == Qt.CheckState.Checked
            self.dataChanged.emit(index, index)
            return True

        return False

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Return item flags — To Group is editable, Confirmed is checkable."""
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_TO:
            return base | Qt.ItemFlag.ItemIsEditable
        if (
            index.column() == COL_CONFIRMED
            and self._mappings[index.row()].to_group is not None
        ):
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def get_mappings(self) -> list[GroupMapping]:
        """Return a copy of the current mappings list."""
        return list(self._mappings)

    def confirm_all(self) -> None:
        """Mark all mapped rows as confirmed."""
        for mapping in self._mappings:
            if mapping.to_group is not None:
                mapping.is_confirmed = True
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(self.rowCount() - 1, len(HEADERS) - 1),
        )

    def to_group_choices(self) -> list[str]:
        """Return the list of To group names plus the Unmapped sentinel."""
        return [g.name for g in self._to_groups] + [_UNMAPPED]


class MappingPage(QWidget):
    """Wizard page 3: review and adjust fuzzy-matched group mappings."""

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._model: MappingTableModel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the mapping table and toolbar."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Review Group Mappings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Each old group has been automatically matched to a new group by name similarity. "
            "Review the suggestions, use the To Group dropdown to correct any wrong matches, "
            "then tick Confirmed for each pair you want to include in the migration."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(4)

        hint = QLabel(
            "Confidence is the name-match score: "
            "green \u2265 80% (high — safe to confirm), "
            "amber 50\u201379% (review recommended), "
            "red < 50% (manual match required). "
            "Only confirmed rows are included in the migration — unconfirmed rows are skipped."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {semantic_color('text_muted')}; font-size: 12px;")
        outer.addWidget(hint)
        outer.addSpacing(8)

        toolbar = QHBoxLayout()
        outer.addLayout(toolbar)

        confirm_all_btn = QPushButton("Confirm All Matches")
        confirm_all_btn.setToolTip("Mark all mapped rows as confirmed")
        confirm_all_btn.clicked.connect(self._confirm_all)
        toolbar.addWidget(confirm_all_btn)
        toolbar.addStretch()

        self._summary_label = QLabel("")
        toolbar.addWidget(self._summary_label)

        self._table = QTableView()
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_CONFIDENCE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_CONFIRMED, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.SelectedClicked
            | QTableView.EditTrigger.CurrentChanged
        )
        outer.addWidget(self._table, stretch=1)

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
        """Re-run the matcher and repopulate the table when page becomes visible."""
        self._demo_banner.setVisible(self._state.demo_mode)
        from_groups = self._state.from_groups
        to_groups = self._state.to_groups
        if not from_groups or not to_groups:
            return

        mappings = match_groups(from_groups, to_groups)
        self._model = MappingTableModel(mappings, to_groups)
        self._model.dataChanged.connect(self._refresh_summary)
        self._table.setModel(self._model)

        delegate = ComboBoxDelegate(self._model.to_group_choices(), parent=self._table)
        self._table.setItemDelegateForColumn(COL_TO, delegate)

        cb_delegate = CheckBoxDelegate(parent=self._table)
        self._table.setItemDelegateForColumn(COL_CONFIRMED, cb_delegate)

        self._refresh_summary()
        logger.info(
            "mapping_page_loaded",
            from_count=len(from_groups),
            mappings=len(mappings),
        )

    def _confirm_all(self) -> None:
        """Confirm all mapped rows."""
        if self._model:
            self._model.confirm_all()
            self._refresh_summary()

    def _refresh_summary(self) -> None:
        """Update the confirmed/total summary label."""
        if self._model is None:
            return
        mappings = self._model.get_mappings()
        confirmed = sum(1 for m in mappings if m.is_confirmed)
        self._summary_label.setText(f"{confirmed} of {len(mappings)} mappings confirmed")

    def validate(self) -> bool:
        """Validate that at least one confirmed mapping exists, then populate AppState."""
        if self._model is None:
            self._error_label.setText("No mappings loaded.")
            return False
        confirmed = [
            m
            for m in self._model.get_mappings()
            if m.is_confirmed and m.to_group is not None
        ]
        if not confirmed:
            self._error_label.setText(
                "Confirm at least one mapping before continuing."
            )
            return False
        self._state.mappings = self._model.get_mappings()
        self._error_label.setText("")
        logger.info("mapping_page_validated", confirmed=len(confirmed))
        return True
