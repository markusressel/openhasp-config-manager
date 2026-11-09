"""The Live device dock: screenshots of the plate of the active tab (with a fake plate)."""

import threading
from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, TEST_DEVICE, copy_test_config


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return copy_test_config(tmp_path, {f"{DEVICE_DIR}/boot.cmd": "run L:/home_page.jsonl\n"})


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Plate:
    """Answers screenshots with an image of the size of the plate (from the background loop)."""

    def __init__(self):
        from PyQt6.QtCore import QBuffer, QIODevice
        from PyQt6.QtGui import QColor, QImage

        image = QImage(480, 320, QImage.Format.Format_RGB32)
        image.fill(QColor("#3366cc"))
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "BMP")
        self.data = bytes(buffer.data())
        self._lock = threading.Lock()
        self._count = 0

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def client(self, _device):
        plate = self

        class _Client:
            async def take_screenshot(self) -> bytes:
                with plate._lock:
                    plate._count += 1
                return plate.data

        return _Client()


@pytest.fixture
def plate(monkeypatch) -> _Plate:
    from openhasp_config_manager.gui.qt.window import live_screens

    plate = _Plate()
    monkeypatch.setattr(live_screens, "OpenHaspClient", plate.client)
    return plate


def _online(window):
    connection = window.connection
    connection._on_broker_changed(connection._generation, True, None)
    connection._on_lwt_received(connection._generation, "online")


class TestLiveDevice(TestBase):
    def test_shows_the_plate_and_refreshes_after_a_restore(self, window, plate):
        # GIVEN
        from openhasp_config_manager.gui.domain.live_screen import ScreenChange
        from openhasp_config_manager.gui.domain.tool_window_rails import Slot

        live = window.live_screens
        clock = live._clock = _Clock()
        assert window.live_device_dock.isHidden()
        assert window.live_device_dock.toggleViewAction() in window.menuBar().actions()[2].menu().actions() or any(
            action is window.live_device_dock.toggleViewAction()
            for menu_action in window.menuBar().actions()
            if menu_action.menu() is not None
            for action in menu_action.menu().actions()
        )
        _online(window)
        # nothing while the dock is closed
        live.refresh()
        assert plate.count == 0

        # WHEN: the dock is shown
        window.show()
        window.live_device_dock.show()
        window.live_device_dock.raise_()

        # THEN: the first image is taken right away
        wait_until(lambda: live.screen_of(TEST_DEVICE).image is not None)
        assert plate.count == 1
        assert live.view.image.image.width() == 480
        assert live.view.status_label.text() == "Updated just now"

        # WHEN: a manual refresh
        live.refresh()

        # THEN
        wait_until(lambda: plate.count == 2 and not live.screen_of(TEST_DEVICE).scheduler.running)

        # WHEN: the plate was restored (also what a deploy reports)
        window.connection.plate_restored()
        live.poll()

        # THEN: once the plate had time to build its pages
        assert plate.count == 2
        clock.now += ScreenChange.RESTORED.delay
        live.poll()
        wait_until(lambda: plate.count == 3)

        # WHEN: another view of its place opens, it closes, and nothing is taken
        wait_until(lambda: not live.screen_of(TEST_DEVICE).scheduler.running)
        window.rails.move("live_device_dock", Slot.BOTTOM_LEFT)
        window.jsonl_dock.show()
        assert window.live_device_dock.isHidden()
        wait_until(lambda: live.screen_of(TEST_DEVICE).scheduler.paused == "hidden")
        window.connection.plate_restored()
        clock.now += 1000
        live.poll()
        assert plate.count == 3

    def test_controls_the_plate_of_the_active_tab(self, window, monkeypatch):
        # GIVEN: the commands reach a fake plate
        from openhasp_config_manager.gui.qt.widgets import device_controls

        sent = []

        class _Client:
            def __init__(self, device):
                self.name = device.name

            async def set_backlight(self, state=None, brightness=None):
                sent.append((self.name, state, brightness))

            async def next_page(self):
                sent.append((self.name, "next"))

        monkeypatch.setattr(device_controls, "OpenHaspClient", _Client)
        controls = window.device_controls
        controls.set_device(controls.device)
        preview = window.page_layout_editor_widget.page_preview_widget

        # THEN: in the Live device dock, for the device of the active tab
        assert window.live_device_dock.isAncestorOf(controls)
        assert controls.device.name == TEST_DEVICE

        # WHEN: the brightness is lowered and the page changed
        controls._brightness_slider.setValue(30)
        wait_until(lambda: (TEST_DEVICE, None, 30) in sent)
        controls.on_next_page_clicked()

        # THEN: the plate gets them, and the preview is darkened like its screen
        wait_until(lambda: (TEST_DEVICE, "next") in sent)
        assert preview._darkness > 0
        assert controls.screen_state(TEST_DEVICE) == (30, True)

        # WHEN: the tab is shown again (another device was active meanwhile)
        controls.set_device(None)
        controls._brightness_slider.setValue(100)
        window._show_tab(window.device_tabs.active)

        # THEN: the slider shows what was set for the device, without sending it again
        assert controls._brightness_slider.value() == 30
        assert [command for command in sent if command[2:] == (100,)] == []
