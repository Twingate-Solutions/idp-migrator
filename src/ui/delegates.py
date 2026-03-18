"""Custom Qt item delegates for twingate-idp-migrator."""

from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)


class CheckBoxDelegate(QStyledItemDelegate):
    """Renders a checkbox in a table cell and handles click-to-toggle reliably.

    Bypasses Qt's internal ItemIsUserCheckable machinery which can have
    inconsistent click behaviour in SelectRows tables.
    """

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Toggle the check state on mouse release if the item allows it."""
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if not (index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        current = index.data(Qt.ItemDataRole.CheckStateRole)
        new_state = (
            Qt.CheckState.Unchecked
            if current == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        return model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)


class ComboBoxDelegate(QStyledItemDelegate):
    """Renders a QComboBox in a table cell for editable choice columns."""

    def __init__(self, choices: list[str], parent: QWidget | None = None) -> None:
        """Initialise with the list of selectable values."""
        super().__init__(parent)
        self._choices = choices

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QComboBox:
        """Create a QComboBox pre-populated with choices and open the popup immediately."""
        combo = QComboBox(parent)
        combo.addItems(self._choices)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, combo.showPopup)
        return combo

    def setEditorData(
        self, editor: QWidget, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Pre-select the item matching the cell's current display value."""
        if not isinstance(editor, QComboBox):
            return
        current = index.data(Qt.ItemDataRole.DisplayRole)
        idx = editor.findText(current or "")
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Write the selected combo value back to the model."""
        if not isinstance(editor, QComboBox):
            return
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Size the combo box to fill the cell rectangle."""
        editor.setGeometry(option.rect)

    def update_choices(self, choices: list[str]) -> None:
        """Replace the choice list (call before editing starts)."""
        self._choices = choices
