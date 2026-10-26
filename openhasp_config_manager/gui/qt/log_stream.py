import asyncio
import logging
from concurrent.futures import Future
from typing import Callable, Optional

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.log_history import LogLinkState
from openhasp_config_manager.gui.qt.async_bridge import get_global_async_loop
from openhasp_config_manager.openhasp_client.logs import LogConnectionEvent, LogEntry
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

LOGGER = logging.getLogger(__name__)


class LogStreamController(QtCore.QObject):
    """
    Streams the log of the selected plate while it is wanted (the Logs panel is visible), and reconnects when the connection is
    lost. The plate allows one telnet connection at a time, so there is none while nobody looks.
    """

    # a new device: what was shown belongs to another plate
    deviceChanged = QtCore.pyqtSignal()
    entriesReceived = QtCore.pyqtSignal(list)  # List[LogEntry]
    stateChanged = QtCore.pyqtSignal(object, str)  # LogLinkState, the error of a lost connection

    # emitted from the asyncio thread, Qt queues them to the main thread; the int is the generation of the stream
    _received = QtCore.pyqtSignal(int, object)

    def __init__(self, parent=None, client_factory: Callable[[Device], OpenHaspClient] = OpenHaspClient):
        super().__init__(parent)
        self._client_factory = client_factory
        self._device: Optional[Device] = None
        self._active = False
        # incremented for every stream, so what a stream that was stopped still sends is ignored
        self._generation = 0
        self._future: Optional[Future] = None
        self.state = LogLinkState.NO_DEVICE
        self._received.connect(self._on_received)

    def set_device(self, device: Optional[Device]):
        """Follow the log of the given device. The device that is followed already (after a reload) is kept."""
        if (device.name if device else None) == (self._device.name if self._device else None):
            self._device = device
            return
        self._device = device
        self._restart()
        self.deviceChanged.emit()

    def set_active(self, active: bool):
        """:param active: whether anybody looks at the log. If not, there is no connection."""
        if active != self._active:
            self._active = active
            self._restart()

    def stop(self):
        self._active = False
        self._restart()

    def _restart(self):
        self._generation += 1
        if self._future is not None:
            self._future.cancel()
            self._future = None
        if self._device is None:
            self._set_state(LogLinkState.NO_DEVICE)
        elif not self._active:
            self._set_state(LogLinkState.INACTIVE)
        else:
            self._set_state(LogLinkState.CONNECTING)
            self._future = asyncio.run_coroutine_threadsafe(
                self._stream(self._client_factory(self._device), self._generation), get_global_async_loop()
            )

    async def _stream(self, client: OpenHaspClient, generation: int):
        try:
            async for item in client.follow_logs(reconnect=True):
                self._received.emit(generation, item)
        except Exception as ex:  # not reachable with reconnect: only a bug ends the stream
            LOGGER.exception(f"The log stream ended: {ex}")
            self._received.emit(generation, LogConnectionEvent(connected=False, error=str(ex)))

    def _on_received(self, generation: int, item):
        if generation != self._generation:
            return
        if isinstance(item, LogEntry):
            self.entriesReceived.emit([item])
        elif item.connected:
            self._set_state(LogLinkState.CONNECTED)
        else:
            self._set_state(LogLinkState.RECONNECTING, item.error or "")

    def _set_state(self, state: LogLinkState, error: str = ""):
        self.state = state
        self.stateChanged.emit(state, error)
