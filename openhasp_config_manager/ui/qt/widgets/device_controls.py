from typing import Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QLayout

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.qt.components import UiComponents
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
        self.layout = UiComponents.create_column(
            parent=self,
            alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )

        self.screen_controls_layout = self._create_screen_controls_layout()
        self.layout.addWidget(UiComponents.create_label(":mdi6.cellphone-screenshot: Screen Controls"))
        self.layout.addLayout(self.screen_controls_layout)

        self.page_controls_layout = self._create_page_controls_layout()
        self.layout.addWidget(UiComponents.create_label(":mdi6.book-open-page-variant: Page Controls"))
        self.layout.addLayout(self.page_controls_layout)

        self.device_controls_layout = self._create_device_controls_layout()
        self.layout.addWidget(UiComponents.create_label(":mdi6.cog: Device Controls"))
        self.layout.addLayout(self.device_controls_layout)

        self.layout.addStretch(1)

    def _create_device_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        button_reboot = UiComponents.create_button(
            title=":power-plug: Reboot Device",
            on_click=self.on_reboot_clicked,
        )
        layout.addWidget(button_reboot)

        return layout

    def _create_screen_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        brightness_slider = UiComponents.create_slider(
            title="Brightness",
            initial_value=100,
            min_value=1,
            on_change=self.__on_brightness_changed
        )

        # TODO: listening to brightness changes from the device
        #     this is harder than anticipated because
        #     1. it requires a continuous async listener to MQTT events, which is difficult in PyQT environment
        #     2. the listener needs to be changed when the device is changed
        #     3. the listener can only be started after a device has been set
        #
        # async def _callback(event_topic: str, event_payload: bytes):
        #     try:
        #         # OpenHASP state payloads are usually JSON: {"text": "12345", "val": 10, ...}
        #         brightness = int(str(event_payload, "utf-8"))
        #         brightness_slider.set_value(brightness)
        #     except Exception:
        #         # If it's not JSON, just return the raw payload
        #         pass
        #
        # async def __listen_brightness():
        #     listen_path = f"state/backlight"
        #     await self.client.listen_event(
        #         path=listen_path,
        #         callback=_callback,
        #     )
        #
        # run_async(__listen_brightness())
        layout.addWidget(brightness_slider)

        button_turn_on = UiComponents.create_button(
            title=":lightbulb-on: Screen ON",
            on_click=self.on_turn_on_clicked,
        )
        layout.addWidget(button_turn_on)

        button_turn_off = UiComponents.create_button(
            title=":lightbulb: Screen OFF",
            on_click=self.on_turn_off_clicked,
        )
        layout.addWidget(button_turn_off)

        return layout

    def _create_page_controls_layout(self) -> QLayout:
        layout = UiComponents.create_row()

        button_prev_page = UiComponents.create_button(
            title=":arrow-left: Previous",
            on_click=self.on_prev_page_clicked,
        )
        layout.addWidget(button_prev_page)

        button_home_page = UiComponents.create_button(
            title=":home:\nHome",
            on_click=self.on_home_page_clicked,
        )
        layout.addWidget(button_home_page)

        button_next_page = UiComponents.create_button(
            title="Next :arrow-right:",
            on_click=self.on_next_page_clicked,
        )
        layout.addWidget(button_next_page)

        return layout

    @qBridge(int)
    def __on_brightness_changed(self, value: int):
        if self.device is None:
            return
        print(f"Setting brightness to {value} for device: {self.device.name}")

        async def __set_brightness():
            await self.client.set_backlight(brightness=value)

        run_async(__set_brightness())

    @qBridge()
    def on_turn_on_clicked(self):
        if self.device is None:
            return
        print(f"Turning on screen for device: {self.device.name}")

        async def __turn_on_screen():
            await self.client.set_backlight(state=True)

        run_async(__turn_on_screen())

    @qBridge()
    def on_turn_off_clicked(self):
        if self.device is None:
            return
        print(f"Turning off screen for device: {self.device.name}")

        async def __turn_off_screen():
            await self.client.set_backlight(state=False)

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
