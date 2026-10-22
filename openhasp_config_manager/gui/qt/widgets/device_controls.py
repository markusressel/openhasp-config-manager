from typing import Optional, Awaitable

from PyQt6.QtWidgets import QWidget, QGroupBox, QMessageBox

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, run_busy, error_text
from openhasp_config_manager.gui.qt.util import run_async, qBridge
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


class DeviceControlsWidget(QWidget):
    """
    Contains controls for a single device, such as buttons to
      - turn the screen on/off
      - reboot the device
      - switch pages
    """

    def __init__(self, status: OperationStatus, parent=None):
        super().__init__(parent)
        self.status = status
        self.device: Optional[Device] = None
        self.client: Optional[OpenHaspClient] = None
        self.busy = BusyState(self)
        self.busy.changed.connect(lambda _: self._update_enabled())

        self._create_layout()
        self._update_enabled()

    def set_device(self, device: Optional[Device]):
        self.device = device
        self.client = None if device is None else OpenHaspClient(device)
        self._update_enabled()

    def _update_enabled(self):
        self._content.setEnabled(self.device is not None and not self.busy.busy)

    def _create_layout(self):
        outer = UiComponents.create_column(parent=self)
        self._content = QWidget()
        outer.addWidget(self._content)
        layout = UiComponents.create_column(parent=self._content)

        screen_group = QGroupBox("Screen")
        screen_layout = UiComponents.create_column(parent=screen_group)
        screen_on_off_row = UiComponents.create_row()
        screen_on_off_row.addWidget(
            UiComponents.create_button(title="On", icon="lightbulb-on", on_click=self.on_turn_on_clicked), 1
        )
        screen_on_off_row.addWidget(
            UiComponents.create_button(title="Off", icon="lightbulb-outline", on_click=self.on_turn_off_clicked), 1
        )
        screen_layout.addLayout(screen_on_off_row)
        screen_layout.addWidget(
            UiComponents.create_slider(
                title="Brightness",
                initial_value=100,
                min_value=1,
                on_change=self.__on_brightness_changed,
            )
        )
        layout.addWidget(screen_group)

        # TODO: listening to brightness changes from the device
        #     this is harder than anticipated because
        #     1. it requires a continuous async listener to MQTT events, which is difficult in PyQT environment
        #     2. the listener needs to be changed when the device is changed
        #     3. the listener can only be started after a device has been set

        page_group = QGroupBox("Pages on the device")
        page_row = UiComponents.create_row(parent=page_group)
        page_row.addWidget(
            UiComponents.create_button(
                title="", icon="arrow-left", tooltip="Previous page", on_click=self.on_prev_page_clicked
            ),
            1,
        )
        page_row.addWidget(
            UiComponents.create_button(title="", icon="home", tooltip="Home page", on_click=self.on_home_page_clicked), 1
        )
        page_row.addWidget(
            UiComponents.create_button(title="", icon="arrow-right", tooltip="Next page", on_click=self.on_next_page_clicked),
            1,
        )
        layout.addWidget(page_group)

        device_group = QGroupBox("Device")
        device_row = UiComponents.create_row(parent=device_group)
        device_row.addWidget(UiComponents.create_button(title="Reboot", icon="restart", on_click=self.on_reboot_clicked), 1)
        layout.addWidget(device_group)

    def _run(self, coro: Awaitable, description: str):
        run_busy(coro, busy=self.busy, status=self.status, description=f"{description} ({self.device.name})")

    @qBridge(int)
    def __on_brightness_changed(self, value: int):
        if self.device is None:
            return
        description = f"Setting the brightness of {self.device.name} to {value}"
        # not run_busy: disabling the slider would interrupt dragging it
        run_async(
            self.client.set_backlight(brightness=value),
            on_error=lambda ex: self.status.failed.emit(description, error_text(ex)),
        )

    @qBridge()
    def on_turn_on_clicked(self):
        self._run(self.client.set_backlight(state=True), "Turning the screen on")

    @qBridge()
    def on_turn_off_clicked(self):
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
