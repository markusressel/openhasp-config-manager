import shutil
from pathlib import Path

import pytest

from tests import TestBase


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
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / "devices" / "test_device" / "boot.cmd").write_text("run L:/home_page.jsonl\n")
    return root


@pytest.fixture
def create_window(settings, async_loop, cfg_root, tmp_path, monkeypatch):
    from openhasp_config_manager.cli.common import _create_config_manager
    from openhasp_config_manager.gui.qt import connection
    from openhasp_config_manager.gui.qt.main import MainWindow

    monkeypatch.setattr(connection, "OpenHaspClient", _FakeConnectionClient)
    windows = []

    def create():
        window = MainWindow(_create_config_manager(cfg_root, tmp_path / "output"))
        windows.append(window)
        return window

    yield create
    for window in windows:
        window.quit_discarding_drafts()


def _wait_until(condition, timeout_ms: int = 5000):
    from PyQt6.QtTest import QTest

    for _ in range(timeout_ms // 10):
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("timed out")


class TestSelectedDeviceIsRemembered(TestBase):
    def test_the_device_of_the_last_session_is_selected_again(self, create_window):
        # GIVEN
        first = create_window()
        _wait_until(lambda: first.devices)
        first.on_device_selected("test_device")
        _wait_until(lambda: first.device is not None)

        # WHEN
        second = create_window()

        # THEN
        _wait_until(lambda: second.device is not None)
        assert second.device.name == "test_device"

    def test_nothing_is_selected_for_another_config_directory(self, create_window, settings):
        # GIVEN
        settings.setValue("devices/selected", "test_device")
        settings.setValue("devices/selected_config_root", "/some/other/configs")

        # WHEN
        window = create_window()
        _wait_until(lambda: window.devices)

        # THEN
        assert window.device is None
        assert window._selected_name is None

    def test_a_device_that_is_gone_is_not_selected(self, create_window, settings, cfg_root):
        # GIVEN
        settings.setValue("devices/selected", "removed_device")
        settings.setValue("devices/selected_config_root", str(cfg_root.resolve()))

        # WHEN
        window = create_window()
        _wait_until(lambda: window.devices)

        # THEN
        assert window._selected_name is None
