"""Theme system — light/dark mode with Twingate brand colors and QSettings persistence."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Checkbox checkmark SVG — referenced by absolute file path (Qt requires this;
# data: URIs are not supported in Qt stylesheet image properties).
# ---------------------------------------------------------------------------

_ICONS_DIR = Path(__file__).parent / "icons"
_CHECK_SVG_PATH = str(_ICONS_DIR / "check.svg").replace("\\", "/")
_CHECK_URL = f'url("{_CHECK_SVG_PATH}")'

# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

LIGHT_COLORS: dict[str, str] = {
    "window_bg": "#f7f8f9",
    "surface": "#ffffff",
    "border": "#e0e1e4",
    "text": "#141617",
    "text_muted": "#5c666a",
    "input_bg": "#ffffff",
    "selection_bg": "#ede9ff",
    "selection_text": "#141617",
    "header_bg": "#f7f8f9",
    "header_border": "#e0e1e4",
    "btn_bg": "#ffffff",
    "btn_hover": "#f0f0f0",
    "btn_disabled_text": "#aaaaaa",
    "btn_disabled_border": "#dddddd",
    "gridline": "#e0e1e4",
    "primary": "#7b66ff",
    "primary_hover": "#6b57ef",
    "success": "#005144",
    "error": "#b71c1c",
    "warning": "#e65100",
}

DARK_COLORS: dict[str, str] = {
    "window_bg": "#0e0f11",
    "surface": "#1d2023",
    "border": "#2e3338",
    "text": "#e0e1e4",
    "text_muted": "#a1a1aa",
    "input_bg": "#1d2023",
    "selection_bg": "#2d2566",
    "selection_text": "#e0e1e4",
    "header_bg": "#141617",
    "header_border": "#2e3338",
    "btn_bg": "#1d2023",
    "btn_hover": "#2a2f35",
    "btn_disabled_text": "#666666",
    "btn_disabled_border": "#555555",
    "gridline": "#2e3338",
    "primary": "#7b66ff",
    "primary_hover": "#8f7dff",
    "success": "#00cbaa",
    "error": "#ef5350",
    "warning": "#ff9800",
}

# ---------------------------------------------------------------------------
# Stylesheet template
# ---------------------------------------------------------------------------

_STYLESHEET_TEMPLATE = """
QMainWindow, QWidget {{
    background-color: {window_bg};
    color: {text};
    font-size: 13px;
}}

#navBar {{
    background-color: {surface};
    border-top: 1px solid {border};
}}

QPushButton {{
    padding: 6px 14px;
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {btn_bg};
    color: {text};
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {btn_hover};
}}
QPushButton[default="true"], QPushButton:default {{
    background-color: {primary};
    color: #ffffff;
    border-color: {primary};
}}
QPushButton[default="true"]:hover, QPushButton:default:hover {{
    background-color: {primary_hover};
    border-color: {primary_hover};
}}
QPushButton:disabled {{
    color: {btn_disabled_text};
    border-color: {btn_disabled_border};
    background-color: {btn_bg};
}}

QLineEdit {{
    padding: 6px 8px;
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {input_bg};
    color: {text};
    font-size: 13px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}
QLineEdit:focus {{
    border-color: {primary};
}}

QLabel {{
    font-size: 13px;
    color: {text};
    background-color: transparent;
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 4px;
    background-color: {surface};
    color: {text};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: {text};
    background-color: {surface};
}}

QCheckBox {{
    color: {text};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border};
    border-radius: 2px;
    background-color: {input_bg};
}}
QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
    image: {check_url};
}}

QAbstractItemView::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {border};
    border-radius: 3px;
    background-color: {input_bg};
}}
QAbstractItemView::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
    image: {check_url};
}}

QRadioButton {{
    color: {text};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border};
    border-radius: 7px;
    background-color: {input_bg};
}}
QRadioButton::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
}}

QTreeWidget, QTreeView {{
    background-color: {input_bg};
    alternate-background-color: {window_bg};
    color: {text};
    border: 1px solid {border};
    gridline-color: {gridline};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}
QTreeWidget::item:selected, QTreeView::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QTableView {{
    background-color: {input_bg};
    alternate-background-color: {window_bg};
    color: {text};
    gridline-color: {gridline};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    border: 1px solid {border};
}}

QHeaderView::section {{
    background-color: {header_bg};
    color: {text};
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid {header_border};
    font-weight: bold;
}}

QListWidget {{
    background-color: {input_bg};
    alternate-background-color: {window_bg};
    color: {text};
    border: 1px solid {border};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}
QListWidget::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QProgressBar {{
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {input_bg};
    text-align: center;
    color: {text};
}}
QProgressBar::chunk {{
    background-color: {primary};
    border-radius: 3px;
}}

QComboBox {{
    padding: 4px 8px;
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {btn_bg};
    color: {text};
    min-width: 80px;
}}
QComboBox:hover {{
    border-color: {primary};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {surface};
    color: {text};
    border: 2px solid {primary};
    border-radius: 4px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    min-width: 220px;
    padding: 2px;
}}

QScrollBar:vertical {{
    background-color: {window_bg};
    width: 12px;
    border: none;
}}
QScrollBar::groove:vertical {{
    background-color: {window_bg};
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background-color: {border};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px 2px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}

QStatusBar {{
    background-color: {surface};
    color: {text_muted};
    border-top: 1px solid {border};
}}

QMenuBar {{
    background-color: {surface};
    color: {text};
    border-bottom: 1px solid {border};
}}
QMenuBar::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}
QMenu {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
}}
QMenu::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}
QMenu::separator {{
    height: 1px;
    background-color: {border};
    margin: 2px 0;
}}
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_SETTINGS_ORG = "Twingate"
_SETTINGS_APP = "IDP Migrator"
_SETTINGS_KEY = "appearance/scheme"

_current_colors: dict[str, str] = dict(LIGHT_COLORS)


class ThemeScheme(StrEnum):
    """User-selectable color scheme."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


def _resolve_scheme(scheme: ThemeScheme) -> ThemeScheme:
    """Resolve SYSTEM to LIGHT or DARK based on the OS color scheme."""
    if scheme != ThemeScheme.SYSTEM:
        return scheme
    hints = QGuiApplication.styleHints()
    from PySide6.QtCore import Qt

    os_scheme = hints.colorScheme()
    if os_scheme == Qt.ColorScheme.Dark:
        return ThemeScheme.DARK
    return ThemeScheme.LIGHT


def apply_theme(app: QApplication, scheme: ThemeScheme) -> None:
    """Apply the given color scheme to the application.

    Resolves SYSTEM to LIGHT or DARK, formats the stylesheet template,
    calls app.setStyleSheet(), updates the module-level color cache,
    and persists the preference to QSettings.
    """
    global _current_colors
    resolved = _resolve_scheme(scheme)
    palette = DARK_COLORS if resolved == ThemeScheme.DARK else LIGHT_COLORS
    _current_colors = dict(palette)
    params = dict(palette)
    params["check_url"] = _CHECK_URL
    stylesheet = _STYLESHEET_TEMPLATE.format(**params)
    app.setStyleSheet(stylesheet)

    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_SETTINGS_KEY, scheme.value)


def apply_initial_theme(app: QApplication) -> None:
    """Load saved scheme preference and apply it, then wire up system theme changes.

    Falls back to ThemeScheme.SYSTEM when no preference is saved.
    Connects colorSchemeChanged so the app reacts if the user toggles
    Windows light/dark mode while the app is running.
    """
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    saved = settings.value(_SETTINGS_KEY, ThemeScheme.SYSTEM.value)
    try:
        scheme = ThemeScheme(saved)
    except ValueError:
        scheme = ThemeScheme.SYSTEM

    apply_theme(app, scheme)

    def _on_system_scheme_changed() -> None:
        current = current_scheme()
        if current == ThemeScheme.SYSTEM:
            apply_theme(app, ThemeScheme.SYSTEM)

    QGuiApplication.styleHints().colorSchemeChanged.connect(_on_system_scheme_changed)


def semantic_color(key: str) -> str:
    """Return the hex color string for the given semantic key in the active palette.

    Keys: success, error, warning, text_muted (and any other palette key).
    """
    return _current_colors.get(key, "#000000")


def current_scheme() -> ThemeScheme:
    """Return the saved user preference (used to set checkmarks in the menu)."""
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    saved = settings.value(_SETTINGS_KEY, ThemeScheme.SYSTEM.value)
    try:
        return ThemeScheme(saved)
    except ValueError:
        return ThemeScheme.SYSTEM
