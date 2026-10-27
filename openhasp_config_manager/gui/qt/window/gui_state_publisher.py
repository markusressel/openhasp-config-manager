import logging
from typing import Any, Callable, Dict

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.gui_state import GuiStateFile

LOGGER = logging.getLogger(__name__)

# state changes are written at most this often: dragging an object changes the state with every mouse move
WRITE_INTERVAL_MS = 300


class GuiStatePublisher(QtCore.QObject):
    """
    Writes the state of the GUI to the state file (see `GuiStateFile`) after it changed, at most every `interval_ms`.
    """

    def __init__(
        self,
        file: GuiStateFile,
        collect: Callable[[bool], Dict[str, Any]],
        interval_ms: int = WRITE_INTERVAL_MS,
        parent=None,
    ):
        """
        :param collect: the current state, for the given `running`
        """
        super().__init__(parent)
        self._file = file
        self._collect = collect
        self._stopped = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._write)

    def request(self):
        """The state changed. A write that is already scheduled picks up this change too."""
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
        except Exception:
            # the state is for other tools: never take the app down for it
            LOGGER.exception("Can't collect the GUI state")
            return
        self._file.write(state)
