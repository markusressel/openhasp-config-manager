import logging
import time
from typing import Callable, Dict, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QImage

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.live_screen import (
    DEFAULT_INTERVAL,
    INTERVALS,
    ScreenChange,
    ScreenshotScheduler,
    reachable,
    status_text,
)
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.operations import error_text
from openhasp_config_manager.gui.qt.widgets.live_screen_view import LiveScreenView
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

LOGGER = logging.getLogger(__name__)

# app-wide: how often the Live device view takes a screenshot (seconds, 0: only after changes)
INTERVAL_SETTINGS_KEY = "live_device/interval"


class _Screen:
    """What the Live device view knows of the plate of one open device."""

    def __init__(self, interval: float):
        self.scheduler = ScreenshotScheduler(interval)
        self.device: Optional[Device] = None
        # the last screenshot that worked, shown again when the tab of the device is
        self.image: Optional[QImage] = None


class LiveScreens(QtCore.QObject):
    """
    The *Live device* dock (`view`): screenshots of the plate of the active tab, kept per open device (by its name) so
    switching tabs shows the last one right away. When to take one is up to the `ScreenshotScheduler` of each device; this
    only asks it at the time it says (one timer, for the active device: only it is shown) and takes the screenshot through
    `run_async`.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._clock = clock
        self._screens: Dict[str, _Screen] = {}
        self._active: Optional[str] = None
        self._visible = False
        value = QSettings().value(INTERVAL_SETTINGS_KEY, DEFAULT_INTERVAL)
        self._interval = int(value) if str(value).isdigit() and int(value) in INTERVALS else DEFAULT_INTERVAL

        self.view = LiveScreenView()
        self.view.set_interval(self._interval)
        self.view.refreshRequested.connect(self.refresh)
        self.view.intervalChanged.connect(self.set_interval)

        # wakes up when the scheduler of the active device wants the next screenshot
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.poll)
        # "updated 12 s ago" while the view is shown
        self._ticker = QtCore.QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._update_view)

    def screen_of(self, name: str) -> _Screen:
        screen = self._screens.get(name)
        if screen is None:
            screen = self._screens[name] = _Screen(self._interval)
        return screen

    # --- what the window reports ---

    def set_device(self, name: str, device: Device):
        """The device of an open tab was loaded (again)."""
        self.screen_of(name).device = device
        self.poll()

    def set_connection(self, name: str, status: ConnectionStatus):
        self.screen_of(name).scheduler.set_reachable(reachable(status.link), self._clock())
        if name == self._active:
            self.poll()

    def screen_changed(self, name: str, change: ScreenChange):
        """The screen of the plate of an open device changed (deploy, Restore plate, Live preview, a command, ...)."""
        if name in self._screens:
            self._screens[name].scheduler.screen_changed(change, self._clock())
            if name == self._active:
                self.poll()

    def show(self, name: Optional[str]):
        """Show the plate of the device of the active tab, None without a tab."""
        if self._active is not None and self._active in self._screens:
            self._screens[self._active].scheduler.set_visible(False)
        self._active = name
        self.view.set_device(name)
        if name is not None:
            self.screen_of(name)
        self._update_visible()

    def set_visible(self, visible: bool):
        """:param visible: whether the dock can be seen (not closed, not behind another dock of its group)"""
        self._visible = visible
        self._update_visible()

    def drop(self, name: str):
        """The last tab of the device was closed: its image goes away (a screenshot that runs is dropped)."""
        self._screens.pop(name, None)
        if name == self._active:
            self.show(None)

    def refresh(self):
        """The user asks for a screenshot of the plate of the active tab."""
        screen = self._active_screen
        if screen is not None:
            screen.scheduler.refresh()
            self.poll()

    def set_interval(self, seconds: int):
        """How often to take a screenshot, for every device; remembered for the next start."""
        self._interval = seconds
        QSettings().setValue(INTERVAL_SETTINGS_KEY, seconds)
        for screen in self._screens.values():
            screen.scheduler.set_interval(seconds)
        self.view.set_interval(seconds)
        self.poll()

    # --- taking them ---

    @property
    def _active_screen(self) -> Optional[_Screen]:
        return None if self._active is None else self._screens.get(self._active)

    def _update_visible(self):
        screen = self._active_screen
        if screen is not None:
            screen.scheduler.set_visible(self._visible)
        if self._visible and screen is not None:
            self._ticker.start()
        else:
            self._ticker.stop()
        self.poll()

    def poll(self):
        """
        Take a screenshot of the active plate if it is due, and wake up when the next one is. The timer calls it; tests call
        it themselves after moving their clock on.
        """
        self._timer.stop()
        screen = self._active_screen
        if screen is not None and screen.device is not None:
            if screen.scheduler.poll(self._clock()):
                self._take(self._active, screen)
            due = screen.scheduler.next_wakeup()
            if due is not None:
                self._timer.start(max(0, int((due - self._clock()) * 1000)) if due != float("-inf") else 0)
        self._update_view()

    def _take(self, name: str, screen: _Screen):
        client = OpenHaspClient(screen.device)

        def __finished(ok: bool, result):
            if self._screens.get(name) is not screen:
                # its tab was closed meanwhile
                return
            now = self._clock()
            if ok:
                image = QImage.fromData(result)
                if image.isNull():
                    screen.scheduler.failed("the plate sent no image", now)
                else:
                    screen.image = image
                    screen.scheduler.succeeded(now)
            else:
                LOGGER.debug(f"Screenshot of {name} failed: {result}")
                screen.scheduler.failed(error_text(result), now)
            if name == self._active:
                self.poll()

        run_async(
            client.take_screenshot(),
            on_success=lambda data: __finished(True, data),
            on_error=lambda ex: __finished(False, ex),
        )

    def _update_view(self):
        screen = self._active_screen
        if screen is None:
            return
        state = screen.scheduler.state()
        self.view.set_image(screen.image)
        self.view.set_busy(state.running)
        self.view.set_status(status_text(state, self._clock()), error=state.error is not None and not state.running)
