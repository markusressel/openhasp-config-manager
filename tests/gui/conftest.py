import os

import pytest


@pytest.fixture(scope="session")
def qapp():
    """A QApplication without a display, for tests of Qt widgets. Skips if PyQt6 (the optional ui group) is missing."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def async_loop(qapp):
    """The background asyncio loop of the GUI (see `async_bridge`), running in its own thread like in the app."""
    import asyncio
    import threading

    from openhasp_config_manager.gui.qt import async_bridge

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    async_bridge.setup_global_async_loop(loop)
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    loop.close()
    async_bridge.setup_global_async_loop(None)


@pytest.fixture
def settings(qapp, tmp_path):
    """QSettings in a temporary directory, never the user's."""
    from PyQt6.QtCore import QCoreApplication, QSettings

    QCoreApplication.setOrganizationName("openhasp-config-manager-test")
    QCoreApplication.setApplicationName("openhasp-config-manager-test")
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return QSettings()
