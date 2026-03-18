"""Entrypoint for twingate-idp-migrator desktop application."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.theme import apply_initial_theme
from src.utils.logging import configure_logging


def main() -> None:
    configure_logging()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Twingate IDP Migrator")
    app.setOrganizationName("Twingate")
    apply_initial_theme(app)

    window = MainWindow()
    window.show()

    # Start the Qt event loop and exit when the window is closed
    exit_code = app.exec()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
