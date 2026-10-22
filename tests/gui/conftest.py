import os

import pytest


@pytest.fixture(scope="session")
def qapp():
    """A QApplication without a display, for tests of Qt widgets. Skips if PyQt6 (the optional ui group) is missing."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
