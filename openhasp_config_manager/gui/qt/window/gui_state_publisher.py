import logging
from typing import Any, Callable, Dict, Optional, Set

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.gui_state import GuiStateFile

LOGGER = logging.getLogger(__name__)

# state changes are written at most this often: dragging an object changes the state with every mouse move
WRITE_INTERVAL_MS = 300


class GuiStatePublisher(QtCore.QObject):
    """
    Writes the state of the GUI to the state file (see `GuiStateFile`) after it changed, at most every `interval_ms`, and the
    images of the plates of the open devices next to it.
    """

    def __init__(
        self,
        file: GuiStateFile,
        collect: Callable[[bool], Dict[str, Any]],
        previews: Optional[Callable[[], Dict[str, Callable[[], bytes]]]] = None,
        interval_ms: int = WRITE_INTERVAL_MS,
        parent=None,
    ):
        """
        :param collect: the current state, for the given `running`
        :param previews: what renders the PNG image of the plate of each open device whose pages are shown, as its tab that
            was active last shows it, by device (None: no images)
        """
        super().__init__(parent)
        self._file = file
        self._collect = collect
        self._previews = previews
        # the devices whose image may have changed since the last write
        self._changed: Set[str] = set()
        self._stopped = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._write)
        # left by an earlier run
        file.remove_device_previews()

    def request(self, device: Optional[str] = None):
        """
        The state changed. A write that is already scheduled picks up this change too.
        :param device: a device whose image may have changed (the image of the active tab is rendered with every write)
        """
        if device is not None:
            self._changed.add(device)
        if not self._stopped and not self._timer.isActive():
            self._timer.start()

    def stop(self):
        """Write the final state: not running anymore."""
        self._stopped = True
        self._timer.stop()
        self._write(running=False)

    def _write(self, running: bool = True):
        try:
            state = self._collect(running)
            renderers = self._previews() if running and self._previews is not None else {}
        except Exception:
            # the state is for other tools: never take the app down for it
            LOGGER.exception("Can't collect the GUI state")
            return
        device: Optional[Dict[str, Any]] = state.get("device")
        active = None if device is None else device["name"]
        previews: Dict[str, Optional[Dict[str, Any]]] = {}
        png = None
        for name, render in renderers.items():
            if name != active and name not in self._changed and self._file.has_device_preview(name):
                previews[name] = self._file.device_preview(name)
                continue
            image = None
            try:
                image = render()
            except Exception:
                LOGGER.exception(f"Can't render the preview of {name} for the GUI state")
            previews[name] = self._file.write_device_preview(name, image)
            if name == active:
                png = image
        self._changed.clear()
        self._file.remove_device_previews(keep=list(renderers))
        # written before the state: the images are the ones the state describes
        preview = self._file.write_preview(png)
        if device is not None:
            device["preview"] = preview
        for tab in state.get("tabs", []):
            tab["preview"] = previews.get(tab["device"])
        self._file.write(state)
