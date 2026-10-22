from typing import Any, Callable

from PyQt6 import QtCore

_NOTHING = object()


class LatestValueThrottle(QtCore.QObject):
    """
    Limits how often a value is sent while it changes quickly (e.g. while dragging a slider): the first value is sent
    right away, then at most one value per interval. The last value is always sent, values in between are dropped.
    """

    def __init__(self, send: Callable[[Any], None], interval_ms: int = 50, parent=None):
        super().__init__(parent)
        self._send = send
        self._pending: Any = _NOTHING
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_timeout)

    def push(self, value: Any):
        if self._timer.isActive():
            self._pending = value
            return
        self._send(value)
        self._timer.start()

    def cancel(self):
        """Drops a value that was not sent yet."""
        self._pending = _NOTHING
        self._timer.stop()

    def _on_timeout(self):
        if self._pending is _NOTHING:
            return
        value, self._pending = self._pending, _NOTHING
        self._send(value)
        self._timer.start()
