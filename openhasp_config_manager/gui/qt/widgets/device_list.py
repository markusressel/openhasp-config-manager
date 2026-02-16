from typing import List

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.util import clear_layout
from openhasp_config_manager.openhasp_client.model.device import Device


class DeviceListWidget(QWidget):
    deviceSelected = QtCore.pyqtSignal(Device)

    def __init__(self):
        super().__init__()
        self.devices = []
        self.layout = UiComponents.create_row(parent=self, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

    def set_devices(self, devices: List[Device]):
        self.devices = devices
        self.clear_entries()
        self.create_entries()

    def clear_entries(self):
        clear_layout(self.layout)

    def create_entries(self):
        sorted_devices = sorted(self.devices, key=lambda d: d.name)
        for device in sorted_devices:

            def __on_device_button_clicked(_, device=device):
                self.on_device_label_clicked(device)

            button = UiComponents.create_button(title=device.name, on_click=__on_device_button_clicked)
            self.layout.addWidget(button)

    def on_device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")
        self.deviceSelected.emit(device)
