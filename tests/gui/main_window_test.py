import shutil
from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until


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
