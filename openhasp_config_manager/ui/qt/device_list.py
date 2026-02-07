from typing import List

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QHBoxLayout

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.components import UiComponents
from openhasp_config_manager.ui.dimensions import UiDimensions
from openhasp_config_manager.ui.qt.util import clear_layout


class DeviceListWidget(QWidget):
    deviceSelected = QtCore.pyqtSignal(Device)

    def __init__(self, devices):
        super().__init__()
        self.devices = devices
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(UiDimensions.one)
        self.create_entries()

    def set_devices(self, devices: List[Device]):
        self.devices = devices
        self.clear_entries()
        self.create_entries()

    def clear_entries(self):
        clear_layout(self.layout)

    def create_entries(self):
        for device in sorted(self.devices, key=lambda d: d.name):
            d = device # needed to capture the current device in the lambda
            def __on_device_button_clicked():
                self.on_device_label_clicked(d)

            button = UiComponents.create_button(title=device.name, on_click=__on_device_button_clicked)
            button.setContentsMargins(10, 10, 10, 10)
            self.layout.addWidget(button)

    def on_device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")
        self.deviceSelected.emit(device)
