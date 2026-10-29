"""
Python's cyclic garbage collector runs in whichever thread happens to allocate when a threshold is reached: also in the thread
of the asyncio loop (`async_bridge`) and its executor threads. Qt objects in reference cycles (e.g. a widget and a lambda slot
that uses it) are then deleted in that thread, and deleting a QWidget outside the main thread corrupts Qt: the app crashes
later, at some random place. So the automatic collection is turned off and the main thread collects instead, with the same
thresholds.
"""

import gc

from PyQt6.QtCore import QObject, QTimer

CHECK_INTERVAL_MS = 100


class MainThreadGarbageCollector(QObject):
    """Turns off the automatic garbage collection and collects in the thread of this object (the main thread) instead."""

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._threshold = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.collect)
        self._timer.start(CHECK_INTERVAL_MS)

    def collect(self):
        """Collects the oldest generation whose count is above its threshold, like the automatic collection would."""
        counts = gc.get_count()
        for generation in (2, 1, 0):
            if counts[generation] > self._threshold[generation]:
                gc.collect(generation)
                return
