"""Main application window — wizard shell with QStackedWidget page flow."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.api.client import TwingateClient
from src.models import GroupMapping, MigrationPlan, TwingateGroup, TwingateResource
from src.ui.theme import ThemeScheme, apply_theme, current_scheme
from src.utils.logging import get_logger

logger = get_logger(__name__)

PAGE_CONNECTION = 0
PAGE_GROUP_SELECTOR = 1
PAGE_MAPPING = 2
PAGE_DRY_RUN = 3    # Session 4
PAGE_EXECUTE = 4    # Session 4
PAGE_ROLLBACK = 5   # Session 4


@dataclass
class AppState:
    """Shared application state that flows through all wizard pages."""

    # Populated by ConnectionPage
    tenant: str = ""
    client: TwingateClient | None = None
    all_groups: list[TwingateGroup] = field(default_factory=list)
    resources: list[TwingateResource] = field(default_factory=list)

    # Populated by GroupSelectorPage
    from_groups: list[TwingateGroup] = field(default_factory=list)
    to_groups: list[TwingateGroup] = field(default_factory=list)

    # Populated by MappingPage
    mappings: list[GroupMapping] = field(default_factory=list)

    # Populated by DryRunPage (Session 4)
    plan: MigrationPlan | None = None

    # Set to True when the user logs in with TEST/TEST credentials
    demo_mode: bool = False


class MainWindow(QMainWindow):
    """Wizard-style main window with QStackedWidget page navigation."""

    def __init__(self) -> None:
        """Set up the main window, pages, and navigation bar."""
        super().__init__()
        self.state = AppState()
        self.setWindowTitle("Twingate IDP Migrator")
        self.setMinimumSize(900, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)
        root.addWidget(self._build_nav_bar())

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._build_menu_bar()
        self._init_pages()
        self._update_nav()

    def _init_pages(self) -> None:
        """Instantiate and register all wizard pages."""
        from src.ui.connection_page import ConnectionPage
        from src.ui.dry_run_page import DryRunPage
        from src.ui.execute_page import ExecutePage
        from src.ui.group_selector_page import GroupSelectorPage
        from src.ui.mapping_page import MappingPage
        from src.ui.rollback_page import RollbackPage

        self._connection_page = ConnectionPage(self.state, self)
        self._group_selector_page = GroupSelectorPage(self.state, self)
        self._mapping_page = MappingPage(self.state, self)
        self._dry_run_page = DryRunPage(self.state, self)
        self._execute_page = ExecutePage(self.state, self)
        self._rollback_page = RollbackPage(self.state, self)

        self._stack.addWidget(self._connection_page)      # 0
        self._stack.addWidget(self._group_selector_page)  # 1
        self._stack.addWidget(self._mapping_page)         # 2
        self._stack.addWidget(self._dry_run_page)         # 3
        self._stack.addWidget(self._execute_page)         # 4
        self._stack.addWidget(self._rollback_page)        # 5

    def _build_nav_bar(self) -> QWidget:
        """Build the bottom navigation bar with Back/Next buttons."""
        bar = QWidget()
        bar.setObjectName("navBar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)

        self._step_label = QLabel("Step 1 of 5")
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._step_label)
        layout.addStretch()

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.clicked.connect(self.go_back)
        layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next →")
        self._next_btn.setMinimumWidth(140)
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self.go_next)
        layout.addWidget(self._next_btn)

        return bar

    def _build_menu_bar(self) -> None:
        """Build the application menu bar."""
        file_menu = self.menuBar().addMenu("&File")
        rollback_action = QAction("&Rollback from Changelog…", self)
        rollback_action.triggered.connect(self._open_rollback_page)
        file_menu.addAction(rollback_action)
        file_menu.addSeparator()

        appearance_menu = file_menu.addMenu("&Appearance")
        scheme_group = QActionGroup(self)
        scheme_group.setExclusive(True)
        saved = current_scheme()
        for label, scheme in [
            ("Use &System Setting", ThemeScheme.SYSTEM),
            ("&Light Mode", ThemeScheme.LIGHT),
            ("&Dark Mode", ThemeScheme.DARK),
        ]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(scheme == saved)
            action.setData(scheme)
            action.triggered.connect(
                lambda checked, s=scheme: apply_theme(QApplication.instance(), s)
            )
            scheme_group.addAction(action)
            appearance_menu.addAction(action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def go_next(self) -> None:
        """Advance to next page if current page validates."""
        widget = self._stack.currentWidget()
        if hasattr(widget, "validate") and not widget.validate():
            return
        nxt = self._stack.currentIndex() + 1
        if nxt < self._stack.count():
            self._stack.setCurrentIndex(nxt)
            next_widget = self._stack.widget(nxt)
            if next_widget is not None and hasattr(next_widget, "on_shown"):
                next_widget.on_shown()
            self._update_nav()

    def go_back(self) -> None:
        """Return to the previous page."""
        if self._stack.currentIndex() > 0:
            self._stack.setCurrentIndex(self._stack.currentIndex() - 1)
            self._update_nav()

    def go_to_page(self, index: int) -> None:
        """Jump directly to a page by index."""
        self._stack.setCurrentIndex(index)
        widget = self._stack.widget(index)
        if widget is not None and hasattr(widget, "on_shown"):
            widget.on_shown()
        self._update_nav()

    def _update_nav(self) -> None:
        """Sync step label and Back/Next button state to current page."""
        idx = self._stack.currentIndex()
        # (label, back_enabled, next_enabled, next_label, next_visible)
        config: dict[int, tuple[str, bool, bool, str, bool]] = {
            PAGE_CONNECTION: (
                "Step 1 of 5: Connect",
                False,
                False,
                "Next →",
                True,
            ),
            PAGE_GROUP_SELECTOR: (
                "Step 2 of 5: Select Groups",
                True,
                True,
                "Next →",
                True,
            ),
            PAGE_MAPPING: (
                "Step 3 of 5: Review Mappings",
                True,
                True,
                "Next →",
                True,
            ),
            PAGE_DRY_RUN: (
                "Step 4 of 5: Preview Changes",
                True,
                True,
                "Run Migration →",
                True,
            ),
            PAGE_EXECUTE: (
                "Step 5 of 5: Execute Migration",
                False,
                False,
                "Next →",
                False,
            ),
            PAGE_ROLLBACK: (
                "Rollback",
                True,
                False,
                "Next →",
                False,
            ),
        }
        label, back_on, next_on, next_label, next_vis = config.get(
            idx, ("", True, True, "Next →", True)
        )
        self._step_label.setText(label)
        self._back_btn.setEnabled(back_on)
        self._next_btn.setEnabled(next_on)
        self._next_btn.setText(next_label)
        self._next_btn.setVisible(next_vis)

    def enable_next(self, enabled: bool) -> None:
        """Enable or disable the Next button (called by pages during async operations)."""
        self._next_btn.setEnabled(enabled)

    def enable_back(self, enabled: bool) -> None:
        """Enable or disable the Back button (called by pages during async operations)."""
        self._back_btn.setEnabled(enabled)

    def set_status(self, message: str) -> None:
        """Display a message in the status bar for 5 seconds."""
        self._status_bar.showMessage(message, 5000)

    def _open_rollback_page(self) -> None:
        """Navigate directly to the Rollback page (accessible via File menu at any time)."""
        self.go_to_page(PAGE_ROLLBACK)
