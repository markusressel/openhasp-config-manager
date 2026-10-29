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


class _FakeConnectionClient:
    """No MQTT connection: the tests must not reach the broker of the test config."""

    def __init__(self, device):
        pass

    def add_connection_listener(self, listener):
        pass

    def remove_connection_listener(self, listener):
        pass

    async def listen_event(self, path, callback):
        pass

    async def cancel_callback(self, callback):
        pass


@pytest.fixture
def create_window(settings, async_loop, cfg_root, tmp_path, monkeypatch):
    """
    Creates main windows for the config directory of the `cfg_root` fixture (which the test module defines), without a
    connection to a plate. The windows are closed after the test, discarding their drafts.
    """
    from openhasp_config_manager.cli.common import _create_config_manager
    from openhasp_config_manager.gui.qt import connection
    from openhasp_config_manager.gui.qt.window.main import MainWindow

    monkeypatch.setattr(connection, "OpenHaspClient", _FakeConnectionClient)
    windows = []

    def create():
        window = MainWindow(_create_config_manager(cfg_root, tmp_path / "output"))
        windows.append(window)
        return window

    yield create
    for window in windows:
        window.quit_discarding_drafts()


@pytest.fixture
def window(create_window):
    """A main window (see `create_window`) with the test device loaded."""
    from tests.gui.helpers import wait_until

    window = create_window()
    wait_until(lambda: window.devices)
    window.on_device_selected("test_device")
    wait_until(lambda: window.session is not None and window.session.is_loaded)
    return window
