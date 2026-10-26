import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.log_history import LogLinkState
from tests import TestBase
from tests.gui.helpers import qwait, wait_until


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / "devices" / "test_device" / "boot.cmd").write_text("run L:/home_page.jsonl\n")
    return root


class TestSelectedDeviceIsRemembered(TestBase):
    def test_the_device_of_the_last_session_is_selected_again(self, create_window):
        # GIVEN
        first = create_window()
        wait_until(lambda: first.devices)
        first.on_device_selected("test_device")
        wait_until(lambda: first.device is not None)

        # WHEN
        second = create_window()

        # THEN
        wait_until(lambda: second.device is not None)
        assert second.device.name == "test_device"

    def test_nothing_is_selected_for_another_config_directory(self, create_window, settings):
        # GIVEN
        settings.setValue("devices/selected", "test_device")
        settings.setValue("devices/selected_config_root", "/some/other/configs")

        # WHEN
        window = create_window()
        wait_until(lambda: window.devices)

        # THEN
        assert window.device is None
        assert window._selected_name is None

    def test_a_device_that_is_gone_is_not_selected(self, create_window, settings, cfg_root):
        # GIVEN
        settings.setValue("devices/selected", "removed_device")
        settings.setValue("devices/selected_config_root", str(cfg_root.resolve()))

        # WHEN
        window = create_window()
        wait_until(lambda: window.devices)

        # THEN
        assert window._selected_name is None


class TestLogsPanel(TestBase):
    def test_is_hidden_and_not_connected_until_it_is_shown(self, create_window):
        # GIVEN
        window = create_window()
        wait_until(lambda: window.devices)
        window.on_device_selected("test_device")
        wait_until(lambda: window.device is not None)

        # THEN
        assert window.logs_dock.isHidden()
        assert window.log_stream.state == LogLinkState.INACTIVE

    def test_connects_only_while_it_is_visible(self, create_window, monkeypatch):
        # GIVEN
        from openhasp_config_manager.gui.qt import main as window_module

        started = []
        monkeypatch.setattr(window_module.LogStreamController, "_restart", lambda self: started.append(self._active))
        window = create_window()
        wait_until(lambda: window.devices)
        window.show()

        # WHEN
        window.logs_dock.show()
        window.logs_dock.raise_()

        # THEN
        wait_until(lambda: window.log_stream._active)

        # WHEN
        window.logs_dock.hide()

        # THEN
        wait_until(lambda: not window.log_stream._active)
        assert started[-2:] == [True, False]


class TestEnableLogColors(TestBase):
    def _window(self, create_window, cfg_root):
        window = create_window()
        wait_until(lambda: window.devices)
        window.on_device_selected("test_device")
        wait_until(lambda: window.device is not None)
        calls = []

        class Client:
            async def set_ansi_colors(self, enabled):
                calls.append(enabled)

        window.log_stream._client_factory = lambda device: Client()
        # the colors are off in the config
        path = window.device.path / "config.json"
        path.write_text(path.read_text().replace('"ansi": 1', '"ansi": 0'))
        return window, calls

    def test_enables_the_colors_at_the_plate_and_in_config_json(self, create_window, cfg_root):
        # GIVEN
        window, calls = self._window(create_window, cfg_root)
        path = window.device.path / "config.json"
        assert '"ansi": 0' in path.read_text()

        # WHEN
        window.enable_log_colors(update_config=True)

        # THEN
        wait_until(lambda: calls == [True])
        assert '"ansi": 1' in path.read_text()
        assert not window._own_writes.foreign([path])

    def test_enables_the_colors_at_the_plate_only(self, create_window, cfg_root):
        # GIVEN
        window, calls = self._window(create_window, cfg_root)
        path = window.device.path / "config.json"
        before = path.read_text()

        # WHEN
        window.enable_log_colors(update_config=False)

        # THEN
        wait_until(lambda: calls == [True])
        assert path.read_text() == before

    def test_a_config_without_the_setting_is_reported_and_nothing_is_sent(self, create_window, cfg_root):
        # GIVEN
        window, calls = self._window(create_window, cfg_root)
        path = window.device.path / "config.json"
        path.write_text('{"debug": {"baud": 1}}')
        failures = []
        window.status.failed.connect(lambda description, error: failures.append(description))

        # WHEN
        window.enable_log_colors(update_config=True)

        # THEN
        assert failures == ["Updating config.json of test_device"]
        qwait(100)
        assert calls == []
