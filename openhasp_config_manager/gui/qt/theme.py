from dataclasses import dataclass
from enum import StrEnum

import qt_themes
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from openhasp_config_manager.gui.dimensions import UiDimensions


class ThemeMode(StrEnum):
    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class ThemeColors:
    qt_theme: str
    error: str
    warning: str
    success: str
    # the area around the plate in the preview
    canvas: str
    # alignment guides and the selection outline in the preview
    accent: str
    # the levels of the log that error, warning and success don't cover
    log_verbose: str
    log_debug: str
    log_received: str


THEMES = {
    ThemeMode.DARK: ThemeColors(
        qt_theme="one_dark_two",
        error="#e27881",
        warning="#e5c07b",
        success="#98c379",
        canvas="#1e2127",
        accent="#ff4fd8",
        log_verbose="#56b6c2",
        log_debug="#61afef",
        log_received="#d19a66",
    ),
    ThemeMode.LIGHT: ThemeColors(
        qt_theme="github_light",
        error="#cf222e",
        warning="#9a6700",
        success="#1a7f37",
        canvas="#d0d7de",
        accent="#d6008f",
        log_verbose="#1b7c83",
        log_debug="#0969da",
        log_received="#bc4c00",
    ),
}

_SETTINGS_KEY = "theme"
_current_mode = ThemeMode.DARK


def current_colors() -> ThemeColors:
    return THEMES[_current_mode]


def current_mode() -> ThemeMode:
    return _current_mode


def load_theme_mode() -> ThemeMode:
    value = QSettings().value(_SETTINGS_KEY, ThemeMode.DARK.value)
    return ThemeMode(value) if value in ThemeMode._value2member_map_ else ThemeMode.DARK


def apply_theme(mode: ThemeMode):
    """
    Apply a theme to the whole application: the palette of the qt_themes theme and one application stylesheet
    for spacing and the semantic roles (hint, error, danger, ...). Widgets set the `role`/`variant` properties
    instead of their own style sheets.
    """
    global _current_mode
    _current_mode = mode
    QSettings().setValue(_SETTINGS_KEY, mode.value)

    colors = THEMES[mode]
    qt_themes.set_theme(colors.qt_theme)
    app = QApplication.instance()
    app.setStyleSheet(_application_stylesheet(app.palette(), colors))


def _rgba(color: QColor, alpha: int) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _application_stylesheet(palette: QPalette, colors: ThemeColors) -> str:
    d = UiDimensions
    text = palette.color(QPalette.ColorRole.WindowText)
    return f"""
QPushButton {{ padding: {d.one}px {d.two}px; }}
QPushButton[variant="danger"] {{ background-color: {colors.error}; color: white; }}
QPushButton[variant="flat"] {{ background: transparent; border: none; padding: 0px; }}
QPushButton[variant="picker"] {{ text-align: left; padding: {d.one}px; }}
QToolBar {{ spacing: {d.half}px; padding: {d.half}px; }}
QToolBar QToolButton {{ padding: {d.half}px; }}
QLineEdit, QSpinBox, QComboBox {{ padding: {d.half}px; }}
QGroupBox {{ font-weight: bold; margin-top: {d.two}px; padding: {d.one}px {d.half}px {d.half}px {d.half}px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {d.one}px; }}
QDockWidget::title {{ padding: {d.half}px {d.one}px; }}
QLabel[role="title"] {{ font-size: 16pt; font-weight: bold; }}
QLabel[role="section"] {{ font-weight: bold; }}
QLabel[role="hint"] {{ color: {_rgba(text, 160)}; }}
QLabel[role="error"] {{ color: {colors.error}; }}
QLabel[role="success"] {{ color: {colors.success}; }}
QLabel[role="icon"] {{ color: {_rgba(text, 160)}; }}
QFrame[role="banner"] {{ background: {_rgba(QColor(colors.error), 40)}; border: 1px solid {colors.error}; border-radius: {d.half}px; }}
QFrame[role="floating"] {{ background: {_rgba(palette.color(QPalette.ColorRole.Window), 235)}; border: 1px solid {_rgba(text, 50)}; border-radius: {d.one}px; }}
QFrame[role="floating"] QToolButton {{ padding: {d.half}px; border-radius: {d.half}px; }}
QFrame[role="floating"] QToolButton:hover {{ background: {_rgba(text, 30)}; }}
QFrame[role="floating"] QToolButton:pressed {{ background: {_rgba(text, 55)}; }}
QFrame[role="floating"] QToolButton:checked {{ background: {_rgba(QColor(colors.accent), 70)}; }}
QFrame[role="floating"] QListWidget {{ background: transparent; border: none; outline: none; }}
QFrame[role="floating"] QListWidget::item {{ padding: {d.half}px; border-radius: {d.half}px; }}
QFrame[role="floating"] QListWidget::item:hover {{ background: {_rgba(text, 25)}; }}
QFrame[role="floating"] QListWidget::item:selected {{ background: {_rgba(text, 45)}; color: {text.name()}; }}
QToolButton[severity="ok"] {{ color: {colors.success}; }}
QToolButton[severity="warning"] {{ color: {colors.warning}; }}
QToolButton[severity="error"] {{ color: {colors.error}; }}
QStatusBar::item {{ border: none; margin: 0px {d.one}px; }}
"""
