import gc
import threading
import weakref

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QWidget  # noqa: E402


class _Cyclic(QWidget):
    def __init__(self):
        super().__init__()
        # a cycle: only the garbage collector frees it
        self.me = self


class TestMainThreadGarbageCollector(TestBase):
    def test_widgets_in_cycles_are_deleted_in_the_main_thread(self, qapp):
        # GIVEN: a widget that only the garbage collector can free
        freed_in = []
        widget = _Cyclic()
        weakref.finalize(widget, lambda: freed_in.append(threading.current_thread()))
        del widget

        # WHEN: another thread allocates far beyond the threshold of the automatic collection
        def allocate():
            for _ in range(10):
                cycles = []
                for _ in range(gc.get_threshold()[0] * 10):
                    cycle = []
                    cycle.append(cycle)
                    cycles.append(cycle)

        thread = threading.Thread(target=allocate)
        thread.start()
        thread.join()

        # THEN: it is still there, and the main thread deletes it
        assert freed_in == []
        wait_until(lambda: freed_in)
        assert freed_in == [threading.main_thread()]
