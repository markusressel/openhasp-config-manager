from typing import Callable, Dict, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QStackedWidget

from openhasp_config_manager.gui.qt.log_stream import LogStreamController
from openhasp_config_manager.gui.qt.widgets.log_view import LogView


class DeviceLog:
    """The log of one open device: its entries (`view`, at most `MAX_ENTRIES`) and its stream."""

    def __init__(self, view: LogView, stream: LogStreamController):
        self.view = view
        self.stream = stream


class DeviceLogs(QtCore.QObject):
    """
    A log per open device tab, kept while the tab is open, so switching tabs shows the earlier entries of a device again. `stack`
    (the Logs dock) shows the log of the active tab. Every log streams while the dock is open, also those of the tabs in the
    background, and none while it is closed: the plate allows one telnet connection, so there is none while nobody looks.
    Without a tab an empty log without a device is shown.
    """

    def __init__(self, on_enable_colors: Callable[[], None], parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._on_enable_colors = on_enable_colors
        self._open = False
        self.stack = QStackedWidget()
        self._logs: Dict[object, DeviceLog] = {}
        self._default = self._create()
        self.active = self._default

    def _create(self) -> DeviceLog:
        view = LogView()
        stream = LogStreamController(self)
        stream.deviceChanged.connect(view.clear)
        stream.entriesReceived.connect(view.add_entries)
        stream.stateChanged.connect(lambda state, error: view.set_link(state, error))
        stream.colorsMissingChanged.connect(view.set_colors_missing)
        view.enableColorsRequested.connect(self._on_enable_colors)
        stream.set_active(self._open)
        self.stack.addWidget(view)
        return DeviceLog(view, stream)

    def log_of(self, key: object) -> DeviceLog:
        """:return: the log of a tab, created the first time"""
        log = self._logs.get(key)
        if log is None:
            log = self._logs[key] = self._create()
        return log

    def show(self, key: Optional[object]):
        """Show the log of a tab, or the empty one (None)."""
        self.active = self._default if key is None else self.log_of(key)
        self.stack.setCurrentWidget(self.active.view)

    def drop(self, key: object):
        """The tab was closed: its log goes away with its entries."""
        log = self._logs.pop(key, None)
        if log is None:
            return
        if log is self.active:
            self.show(None)
        log.stream.stop()
        self.stack.removeWidget(log.view)
        log.view.deleteLater()
        log.stream.deleteLater()

    def set_open(self, open_: bool):
        """:param open_: whether the Logs dock is open (shown, raised or not): all logs stream while it is"""
        self._open = open_
        for log in self.logs:
            log.stream.set_active(open_)

    def stop(self):
        for log in self.logs:
            log.stream.stop()

    @property
    def logs(self):
        return [self._default, *self._logs.values()]

    def refresh_theme(self):
        for log in self.logs:
            log.view.refresh_theme()
