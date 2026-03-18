"""Connection page — wizard step 1: tenant name + API key entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.api.client import TwingateClient
from src.ui.demo_data import (
    DEMO_FROM_GROUPS,
    DEMO_GROUPS,
    DEMO_MAPPINGS,
    DEMO_RESOURCES,
    DEMO_TO_GROUPS,
)
from src.ui.theme import semantic_color
from src.ui.workers import ConnectWorker, FetchResult, FetchWorker
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.ui.main_window import AppState, MainWindow

logger = get_logger(__name__)


class ConnectionPage(QWidget):
    """Wizard page 1: enter Twingate credentials and connect.

    On success: AppState.client, .tenant, .all_groups, .resources are populated.
    """

    def __init__(self, state: AppState, main_window: MainWindow) -> None:
        """Initialise with shared app state and a reference to the main window."""
        super().__init__()
        self._state = state
        self._mw = main_window
        self._connect_worker: ConnectWorker | None = None
        self._fetch_worker: FetchWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the credential form and status label."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        title = QLabel("Connect to Twingate")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Enter your Twingate tenant name and API key to load your groups and resources. "
            "No changes are made at this step — the tool only reads data until Execute."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        outer.addSpacing(24)

        group = QGroupBox("Twingate API Credentials")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._tenant_edit = QLineEdit()
        self._tenant_edit.setPlaceholderText("e.g. acme  (enter TEST to use demo data)")
        self._tenant_edit.setMaximumWidth(340)
        form.addRow("Tenant Name:", self._tenant_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setPlaceholderText("Paste API key here  (enter TEST for demo)")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setMaximumWidth(340)
        form.addRow("API Key:", self._api_key_edit)

        outer.addWidget(group)

        help_text = QLabel(
            "Tenant name: the subdomain of your Twingate admin URL — "
            "if you access app.twingate.com/acme, enter acme.\n"
            "API key: generate one in the Twingate admin console under Settings → API Keys "
            "with Read and Write permissions.\n"
            "Demo mode: enter TEST in both fields to walk through the tool with sample data."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            f"color: {semantic_color('text_muted')}; font-size: 12px; padding-top: 6px;"
        )
        outer.addWidget(help_text)
        outer.addSpacing(8)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(120)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        outer.addWidget(self._connect_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)
        outer.addStretch()

        self._mw.enable_next(False)

    def validate(self) -> bool:
        """Return True only if we have a connected client."""
        if self._state.client is None:
            self._set_error("Please connect before continuing.")
            return False
        return True

    def _on_connect_clicked(self) -> None:
        """Validate inputs and launch the ConnectWorker (or activate demo mode)."""
        tenant = self._tenant_edit.text().strip()
        api_key = self._api_key_edit.text().strip()
        if not tenant:
            self._set_error("Tenant name is required.")
            return
        if not api_key:
            self._set_error("API key is required.")
            return

        if tenant.upper() == "TEST" and api_key.upper() == "TEST":
            self._activate_demo_mode()
            return

        self._set_status("Connecting…")
        self._connect_btn.setEnabled(False)
        self._mw.enable_next(False)
        client = TwingateClient(tenant=tenant, api_key=api_key)
        self._connect_worker = ConnectWorker(client)
        self._connect_worker.finished.connect(lambda ok: self._on_connected(ok, client))
        self._connect_worker.error.connect(self._on_error)
        self._connect_worker.start()

    def _activate_demo_mode(self) -> None:
        """Populate AppState with sample data and skip real API calls."""
        self._state.demo_mode = True
        self._state.tenant = "demo"
        self._state.client = TwingateClient(tenant="demo", api_key="demo")
        self._state.all_groups = list(DEMO_GROUPS)
        self._state.resources = list(DEMO_RESOURCES)
        self._state.from_groups = list(DEMO_FROM_GROUPS)
        self._state.to_groups = list(DEMO_TO_GROUPS)
        self._state.mappings = list(DEMO_MAPPINGS)
        self._status_label.setText(
            "Demo mode active — using sample data (Okta → Entra ID scenario). "
            "Click Next to continue."
        )
        self._status_label.setStyleSheet(
            f"color: {semantic_color('warning')}; font-weight: bold;"
        )
        self._mw.enable_next(True)

    def _on_connected(self, ok: bool, client: TwingateClient) -> None:
        """Handle ConnectWorker result — start FetchWorker on success."""
        if not ok:
            self._set_error("Connection failed. Check tenant name and API key.")
            self._connect_btn.setEnabled(True)
            return
        self._set_status("Connected. Fetching groups and resources…")
        self._fetch_worker = FetchWorker(client)
        self._fetch_worker.finished.connect(lambda r: self._on_fetched(r, client))
        self._fetch_worker.error.connect(self._on_error)
        self._fetch_worker.start()

    def _on_fetched(self, result: FetchResult, client: TwingateClient) -> None:
        """Handle FetchWorker result — populate AppState and unlock Next."""
        self._state.tenant = self._tenant_edit.text().strip()
        self._state.client = client
        self._state.all_groups = result.groups
        self._state.resources = result.resources
        g, r = len(result.groups), len(result.resources)
        self._set_status(f"Connected. Loaded {g} groups and {r} resources.")
        self._status_label.setStyleSheet(f"color: {semantic_color('success')};")
        self._connect_btn.setEnabled(True)
        self._mw.enable_next(True)
        logger.info("connection_page_fetched", tenant=self._state.tenant, groups=g, resources=r)

    def _on_error(self, message: str) -> None:
        """Handle worker error — show inline error and re-enable Connect."""
        self._set_error(message)
        self._connect_btn.setEnabled(True)

    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {semantic_color('text_muted')};")

    def _set_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")
        self._status_label.setStyleSheet(f"color: {semantic_color('error')};")
