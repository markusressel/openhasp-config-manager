from typing import Optional

from PyQt6.QtWidgets import QWidget, QLayout

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.components import UiComponents
from openhasp_config_manager.ui.qt.util import run_async, qBridge


class DeviceControlsWidget(QWidget):
    """
    Contains controls for a single device, such as buttons to
      - turn the screen on/off
      - reboot the device
      - switch pages
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device: Optional[Device] = None

        self._create_layout()

    def set_device(self, device: Optional[Device]):
        self.device = device
        self.client = OpenHaspClient(self.device)

    def _create_layout(self):
        self.main_layout = UiComponents.create_column()
        self.setLayout(self.main_layout)

        self.device_controls_layout = self._create_device_controls_layout()
        self.main_layout.addLayout(self.device_controls_layout)

        self.screen_controls_layout = self._create_screen_controls_layout()
        self.main_layout.addLayout(self.screen_controls_layout)

        self.page_controls_layout = self._create_page_controls_layout()
        self.main_layout.addLayout(self.page_controls_layout)

    def _create_device_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        button_reboot = UiComponents.create_button(
            title="Reboot Device",
            on_click=self.on_reboot_clicked,
        )
        layout.addWidget(button_reboot)

        return layout

    def _create_screen_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        button_turn_on = UiComponents.create_button(
            title="Turn Screen ON",
            on_click=self.on_turn_on_clicked,
        )
        layout.addWidget(button_turn_on)

        button_turn_off = UiComponents.create_button(
            title="Turn Screen OFF",
            on_click=self.on_turn_off_clicked,
        )
        layout.addWidget(button_turn_off)

        return layout

    def _create_page_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        button_prev_page = UiComponents.create_button(
            title="Previous Page",
            on_click=self.on_prev_page_clicked,
        )
        layout.addWidget(button_prev_page)

        button_home_page = UiComponents.create_button(
            title="Home Page",
            on_click=self.on_home_page_clicked,
        )
        layout.addWidget(button_home_page)

        button_next_page = UiComponents.create_button(
            title="Next Page",
            on_click=self.on_next_page_clicked,
        )
        layout.addWidget(button_next_page)

        return layout

    @qBridge()
    def on_turn_on_clicked(self):
        if self.device is None:
            return
        print(f"Turning on screen for device: {self.device.name}")

        async def __turn_on_screen():
            await self.client.set_backlight(True, None)

        run_async(__turn_on_screen())

    @qBridge()
    def on_turn_off_clicked(self):
        if self.device is None:
            return
        print(f"Turning off screen for device: {self.device.name}")

        async def __turn_off_screen():
            await self.client.set_backlight(False, None)

        run_async(__turn_off_screen())

    @qBridge()
    def on_reboot_clicked(self):
        if self.device is None:
            return
        print(f"Rebooting device: {self.device.name}")

        async def __reboot_device():
            self.client.reboot()

        run_async(__reboot_device())

    @qBridge()
    def on_prev_page_clicked(self):
        if self.device is None:
            return
        print(f"Switching to previous page on device: {self.device.name}")

        async def __prev_page():
            await self.client.previous_page()

        run_async(__prev_page())

    @qBridge()
    def on_home_page_clicked(self):
        if self.device is None:
            return
        print(f"Switching to home page on device: {self.device.name}")

        async def __home_page():
            await self.client.set_page(1)

        run_async(__home_page())

    @qBridge()
    def on_next_page_clicked(self):
        if self.device is None:
            return
        print(f"Switching to next page on device: {self.device.name}")

        async def __next_page():
            await self.client.next_page()

        run_async(__next_page())
