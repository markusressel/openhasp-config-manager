from typing import Optional, Awaitable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QMessageBox, QSlider, QToolButton, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, run_busy, error_text
from openhasp_config_manager.gui.qt.async_bridge import run_async, qBridge
from openhasp_config_manager.gui.qt.throttle import LatestValueThrottle
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


class DeviceControlsWidget(QWidget):
    """
    A compact bar with controls for a single device (it floats on the preview), such as buttons to
      - turn the screen on/off
      - reboot the device
      - switch pages
    """

    # the brightness (1..100) and whether the screen is on, to show it in the preview
    screenChanged = pyqtSignal(int, bool)

    def __init__(self, status: OperationStatus, parent=None):
        super().__init__(parent)
        self.status = status
        self.device: Optional[Device] = None
        self.client: Optional[OpenHaspClient] = None
        self.busy = BusyState(self)
        self.busy.changed.connect(lambda _: self._update_enabled())
        # dragging the slider changes the value many times per second: one command per value would flood MQTT
        self._brightness = LatestValueThrottle(self._set_brightness, interval_ms=50, parent=self)

        self._create_layout()
        self._update_enabled()

    def set_device(self, device: Optional[Device]):
        # a brightness for the previous device must not reach the new one
        self._brightness.cancel()
        self.device = device
        self.client = None if device is None else OpenHaspClient(device)
        self._update_enabled()

    def _update_enabled(self):
        self._content.setEnabled(self.device is not None and not self.busy.busy)

    def _create_layout(self):
        outer = UiComponents.create_row(parent=self)
        self._content = QWidget()
        outer.addWidget(self._content)
        layout = UiComponents.create_row(parent=self._content)

        def button(icon: str, tooltip: str, on_click) -> QToolButton:
            result = QToolButton()
            ThemedIcons.apply(result, icon)
            result.setToolTip(tooltip)
            result.setAutoRaise(True)
            result.setCursor(Qt.CursorShape.PointingHandCursor)
            result.clicked.connect(lambda _checked=False: on_click())
            # keep the keyboard focus on the plate, for its shortcuts
            result.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return result

        layout.addWidget(button("lightbulb-on", "Turn the screen on", self.on_turn_on_clicked))
        layout.addWidget(button("lightbulb-outline", "Turn the screen off", self.on_turn_off_clicked))
        brightness = QSlider(Qt.Orientation.Horizontal)
        brightness.setRange(1, 100)
        brightness.setValue(100)
        brightness.setFixedWidth(UiDimensions.five * 4)
        brightness.setToolTip("Brightness of the screen. The preview is darkened the same way.")
        brightness.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        brightness.valueChanged.connect(self.__on_brightness_changed)
        self._brightness_slider = brightness
        layout.addWidget(brightness)

        layout.addWidget(self._separator())
        layout.addWidget(button("arrow-left", "Previous page on the device", self.on_prev_page_clicked))
        layout.addWidget(button("home", "Home page on the device", self.on_home_page_clicked))
        layout.addWidget(button("arrow-right", "Next page on the device", self.on_next_page_clicked))

        layout.addWidget(self._separator())
        layout.addWidget(button("restart", "Reboot the device", self.on_reboot_clicked))

        # TODO: listening to brightness changes from the device
        #     this is harder than anticipated because
        #     1. it requires a continuous async listener to MQTT events, which is difficult in PyQT environment
        #     2. the listener needs to be changed when the device is changed
        #     3. the listener can only be started after a device has been set

    @staticmethod
    def _separator() -> QFrame:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator

    def _run(self, coro: Awaitable, description: str):
        run_busy(coro, busy=self.busy, status=self.status, description=f"{description} ({self.device.name})")

    @qBridge(int)
    def __on_brightness_changed(self, value: int):
        self.screenChanged.emit(value, True)
        if self.device is None:
            return
        self._brightness.push(value)

    def _set_brightness(self, value: int):
        description = f"Setting the brightness of {self.device.name} to {value}"
        # not run_busy: disabling the slider would interrupt dragging it
        run_async(
            self.client.set_backlight(brightness=value),
            on_error=lambda ex: self.status.failed.emit(description, error_text(ex)),
        )

    @qBridge()
    def on_turn_on_clicked(self):
        self.screenChanged.emit(self._brightness_slider.value(), True)
        self._run(self.client.set_backlight(state=True), "Turning the screen on")

    @qBridge()
    def on_turn_off_clicked(self):
        self.screenChanged.emit(self._brightness_slider.value(), False)
        self._run(self.client.set_backlight(state=False), "Turning the screen off")

    @qBridge()
    def on_reboot_clicked(self):
        answer = QMessageBox.question(
            self,
            "Reboot device",
            f"Reboot {self.device.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run(self.client.reboot(), "Rebooting")

    @qBridge()
    def on_prev_page_clicked(self):
        self._run(self.client.previous_page(), "Switching to the previous page")

    @qBridge()
    def on_home_page_clicked(self):
        self._run(self.client.set_page(1), "Switching to the home page")

    @qBridge()
    def on_next_page_clicked(self):
        self._run(self.client.next_page(), "Switching to the next page")
