from typing import Any, Awaitable, Callable, Optional

from PyQt6 import QtCore

from openhasp_config_manager.gui.qt.util import run_async


class BusyState(QtCore.QObject):
    """
    Counts the running operations of a part of the UI. Widgets disable their controls while it is busy,
    and it is restored when an operation finished, also when it failed.
    """

    changed = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0

    @property
    def busy(self) -> bool:
        return self._count > 0

    def enter(self):
        self._count += 1
        if self._count == 1:
            self.changed.emit(True)

    def leave(self):
        self._count -= 1
        if self._count == 0:
            self.changed.emit(False)


class OperationStatus(QtCore.QObject):
    """
    Reports the background operations of the window, shown in the status bar.
    The signals can be emitted from the asyncio thread, Qt queues them to the main thread.
    """

    started = QtCore.pyqtSignal(str)  # description
    progressed = QtCore.pyqtSignal(int, int)  # done, total
    succeeded = QtCore.pyqtSignal(str)  # message
    failed = QtCore.pyqtSignal(str, str)  # description, error

    def report_progress(self, done: int, total: int):
        self.progressed.emit(done, total)


def error_text(ex: Exception) -> str:
    return str(ex) or type(ex).__name__


def run_busy(
    coro: Awaitable,
    busy: BusyState,
    status: OperationStatus,
    description: str,
    success_message: Optional[str] = None,
    on_success: Callable[[Any], None] = None,
    on_error: Callable[[Exception], None] = None,
):
    """
    Run a coroutine in the background like `run_async`, keeping `busy` busy and reporting it to `status` until it finished.

    :param description: what the operation does, e.g. "Deploying page 1"
    :param success_message: the status message when it succeeded, defaults to "<description>: done"
    """
    busy.enter()
    status.started.emit(description)

    def __on_success(result):
        status.succeeded.emit(success_message or f"{description}: done")
        if on_success is not None:
            on_success(result)

    def __on_error(ex: Exception):
        status.failed.emit(description, error_text(ex))
        if on_error is not None:
            on_error(ex)

    return run_async(coro, on_done=busy.leave, on_success=__on_success, on_error=__on_error)
