from typing import List

from PyQt6.QtWidgets import QWidget, QMainWindow, QPushButton, QVBoxLayout

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.util import clear_layout


class DeviceListWidget(QWidget):
    def __init__(self, devices):
        super().__init__()
        self.devices = devices
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.create_entries()

    def set_devices(self, devices: List[Device]):
        self.devices = devices
        self.clear_entries()
        self.create_entries()

    def clear_entries(self):
        clear_layout(self.layout)

    def create_entries(self):
        for device in sorted(self.devices, key=lambda d: d.name):
            button = QPushButton(device.name)
            button.clicked.connect(lambda _, d=device: self.on_device_label_clicked(d))
            self.layout.addWidget(button)

    def on_device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager

        self.setWindowTitle("openhasp-config-manager")

        self.create_basic_layout()
        self.load_plates()

    def the_button_was_clicked(self):
        print("Clicked!")

    def create_basic_layout(self):
        self.devices_container = DeviceListWidget(devices=[])
        self.setCentralWidget(self.devices_container)

    def load_plates(self):
        self.devices = self.config_manager.analyze()
        self.devices_container.set_devices(self.devices)
