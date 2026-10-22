import logging
from typing import Optional, Callable, Awaitable

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.qt.operations import error_text
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

LOGGER = logging.getLogger(__name__)


class ConnectionController(QtCore.QObject):
    """
    Keeps an MQTT connection to the broker of the selected plate and follows the plate's LWT topic,
    so the status bar can show whether the broker and the plate are reachable. Also tracks whether something is
    being sent and which pages are out of sync after a failed send.
    """

    changed = QtCore.pyqtSignal(object)  # ConnectionStatus

    # emitted from the asyncio thread, Qt queues them to the main thread; the int is the generation of the device
    _brokerChanged = QtCore.pyqtSignal(int, bool, object)
    _lwtReceived = QtCore.pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = ConnectionStatus()
        # incremented for every device, so events of the previous device's connection are ignored
        self._generation = 0
        self._device_name: Optional[str] = None
        self._client: Optional[OpenHaspClient] = None
        self._connection_listener: Optional[Callable[[bool, Optional[Exception]], None]] = None
        self._lwt_callback: Optional[Callable[[str, bytes], Awaitable[None]]] = None

        self._brokerChanged.connect(self._on_broker_changed)
        self._lwtReceived.connect(self._on_lwt_received)

    def set_device(self, device: Optional[Device]):
        """
        Follow the given device. Selecting the device that is already followed (after a reload) keeps its status.
        """
        name = None if device is None else device.name
        if name == self._device_name:
            return
        self._device_name = name
        self._stop()
        self._generation += 1
        if device is None:
            self._set(ConnectionStatus())
            return

        generation = self._generation
        client = OpenHaspClient(device)

        def _on_connection(connected: bool, error: Optional[Exception]):
            self._brokerChanged.emit(generation, connected, None if error is None else error_text(error))

        async def _on_lwt(_topic: str, payload: bytes):
            self._lwtReceived.emit(generation, payload.decode("utf-8"))

        self._client = client
        self._connection_listener = _on_connection
        self._lwt_callback = _on_lwt
        self._set(ConnectionStatus.connecting())

        client.add_connection_listener(_on_connection)
        run_async(client.listen_event(path="LWT", callback=_on_lwt))

    def stop(self):
        self._stop()

    def _stop(self):
        if self._client is None:
            return
        self._client.remove_connection_listener(self._connection_listener)
        run_async(self._client.cancel_callback(callback=self._lwt_callback))
        self._client = None
        self._connection_listener = None
        self._lwt_callback = None

    def set_sending(self, sending: bool):
        self._set(self.status.with_sending(sending))

    def page_out_of_sync(self, page: int):
        self._set(self.status.with_send_failed(page))

    def page_deployed(self, page: int):
        self._set(self.status.with_page_deployed(page))

    def _on_broker_changed(self, generation: int, connected: bool, error: Optional[str]):
        if generation == self._generation:
            self._set(self.status.with_broker(connected, error))

    def _on_lwt_received(self, generation: int, payload: str):
        if generation == self._generation:
            LOGGER.debug(f"LWT of the plate: {payload}")
            self._set(self.status.with_lwt(payload))

    def _set(self, status: ConnectionStatus):
        if status != self.status:
            self.status = status
            self.changed.emit(status)
