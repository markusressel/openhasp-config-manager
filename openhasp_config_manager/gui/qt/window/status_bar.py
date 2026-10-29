from typing import Callable, Optional

import qtawesome as qta
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QProgressBar, QToolButton

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.connection import ConnectionStatus, LinkState, Severity
from openhasp_config_manager.gui.domain.draft.page_objects import page_label
from openhasp_config_manager.gui.qt.operations import OperationStatus
from openhasp_config_manager.gui.qt.theme import current_colors


def severity_color(severity: Severity) -> QColor:
    colors = current_colors()
    return {
        Severity.NEUTRAL: QApplication.palette().color(QPalette.ColorRole.PlaceholderText),
        Severity.OK: QColor(colors.success),
        Severity.WARNING: QColor(colors.warning),
        Severity.ERROR: QColor(colors.error),
    }[severity]


def connection_icon(connection_status: ConnectionStatus, live: bool = False) -> QIcon:
    """The dot of a connection (in the color of its state), or the Live preview icon in that color while it is on."""
    return qta.icon("mdi6.broadcast" if live else "mdi6.circle", color=severity_color(connection_status.summary[1]))


class StatusBarController:
    """
    Shows the device of the active tab, the connection to it, the page, the draft state and the last operation in the status bar.
    """

    def __init__(self, window: QMainWindow, status: OperationStatus, on_resync: Callable[[int], None]):
        bar = window.statusBar()
        self._on_resync = on_resync
        self._connection_status = ConnectionStatus()
        self._connection = QToolButton()
        self._connection.setAutoRaise(True)
        self._connection.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._connection.clicked.connect(self._on_connection_clicked)
        self._device = QLabel("No device")
        self._page = QLabel("")
        self._dirty = QLabel("")
        self._operation = QLabel("Ready")
        self._operation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(160)
        self._progress.setMaximumHeight(UiDimensions.two)
        self._progress.hide()

        bar.addWidget(self._operation, 1)
        bar.addPermanentWidget(self._progress)
        bar.addPermanentWidget(self._dirty)
        bar.addPermanentWidget(self._page)
        bar.addPermanentWidget(self._device)
        bar.addPermanentWidget(self._connection)

        status.started.connect(self._on_started)
        status.progressed.connect(self._on_progressed)
        status.succeeded.connect(self._on_succeeded)
        status.failed.connect(self._on_failed)
        self._running = 0

    def set_device(self, name: Optional[str]):
        self._device.setText(name or "No device")

    def set_connection(self, connection_status: ConnectionStatus):
        self._connection_status = connection_status
        text, severity = connection_status.summary
        self._connection.setVisible(connection_status.link != LinkState.NO_DEVICE)
        self._connection.setText(text)
        self._connection.setIcon(connection_icon(connection_status))
        self._connection.setToolTip(connection_status.details)
        self._connection.setProperty("severity", severity.value)
        self._connection.style().unpolish(self._connection)
        self._connection.style().polish(self._connection)

    def refresh_theme(self):
        self.set_connection(self._connection_status)

    def _on_connection_clicked(self):
        if self._connection_status.out_of_sync_pages:
            self._on_resync(min(self._connection_status.out_of_sync_pages))

    def set_page(self, index: Optional[int], count: int = 0):
        self._page.setText("" if index is None else f"{page_label(index)}  ·  {count} pages")

    def set_dirty(self, dirty: bool):
        self._dirty.setText("● Modified" if dirty else "")
        self._dirty.setToolTip("The draft differs from the files on disk. Changes are kept until the app is closed.")

    def _set_operation(self, text: str, role: Optional[str] = None):
        self._operation.setText(text)
        self._operation.setProperty("role", role)
        self._operation.style().unpolish(self._operation)
        self._operation.style().polish(self._operation)

    def _on_started(self, description: str):
        self._running += 1
        self._set_operation(f"{description}…")
        self._progress.setRange(0, 0)  # indeterminate until progress is reported
        self._progress.show()

    def _on_progressed(self, done: int, total: int):
        self._progress.setRange(0, total)
        self._progress.setValue(done)

    def _on_succeeded(self, message: str):
        self._finish()
        self._set_operation(message, "success")

    def _on_failed(self, description: str, error: str):
        self._finish()
        self._set_operation(f"{description} failed: {error}", "error")

    def _finish(self):
        self._running = max(0, self._running - 1)
        if self._running == 0:
            self._progress.hide()
