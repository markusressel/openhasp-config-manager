import logging
from pathlib import Path
from typing import Iterable, List, Optional, Set

from PyQt6 import QtCore
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from openhasp_config_manager.gui.domain.config_changes import is_relevant_change

LOGGER = logging.getLogger(__name__)

# the changes of a burst (an LLM or a script writing several files, an editor saving through a temporary file) are
# reported together, this long after the last of them
DEBOUNCE_MS = 400

_CHANGE_EVENTS = {"created", "modified", "deleted", "moved"}


class ConfigWatcher(QtCore.QObject):
    """
    Watches a config directory recursively and reports the paths that changed, debounced. Runs the watchdog observer
    in its own thread; the signal is emitted in the thread of the watcher (the main thread).
    """

    changed = QtCore.pyqtSignal(object)  # Set[Path]
    _event = QtCore.pyqtSignal(object)  # Set[Path], from the observer thread

    def __init__(self, root: Path, ignored_roots: Iterable[Path] = (), debounce_ms: int = DEBOUNCE_MS, parent=None):
        super().__init__(parent)
        self._root = root
        self._ignored_roots = list(ignored_roots)
        self._pending: Set[Path] = set()
        self._observer: Optional[Observer] = None

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._flush)
        # emitted from the observer thread: Qt queues it to the thread of this object
        self._event.connect(self._on_event)

    def start(self):
        if self._observer is not None:
            return
        handler = _Handler(self._ignored_roots, self._event.emit)
        observer = Observer()
        observer.schedule(handler, str(self._root), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer
        LOGGER.debug(f"Watching {self._root} for changes")

    def stop(self):
        self._timer.stop()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def _on_event(self, paths: Set[Path]):
        self._pending |= paths
        self._timer.start()

    def _flush(self):
        paths, self._pending = self._pending, set()
        if paths:
            self.changed.emit(paths)


class _Handler(FileSystemEventHandler):
    def __init__(self, ignored_roots: List[Path], emit):
        self._ignored_roots = ignored_roots
        self._emit = emit

    def on_any_event(self, event: FileSystemEvent):
        if event.event_type not in _CHANGE_EVENTS:
            # opened, closed, ...: reading a file is not a change
            return
        if event.is_directory and event.event_type == "modified":
            # reported for the folder of every changed file
            return
        paths = {Path(str(p)) for p in (event.src_path, getattr(event, "dest_path", "")) if p}
        paths = {path for path in paths if is_relevant_change(path, self._ignored_roots)}
        if paths:
            self._emit(paths)
