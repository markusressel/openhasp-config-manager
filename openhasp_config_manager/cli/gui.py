import sys
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device


class DeviceListWidget(QWidget):
    def __init__(self, devices):
        super().__init__()
        self.devices = devices
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.create_entries()

    def device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")

    def set_devices(self, devices: List[Device]):
        self.devices = devices
        self.clear_entries()
        self.create_entries()

    def create_entries(self):
        for device in sorted(self.devices, key=lambda d: d.name):
            button = QPushButton(device.name)
            button.clicked.connect(lambda _, d=device: self.device_label_clicked(d))
            self.layout.addWidget(button)

    def clear_entries(self):
        for i in reversed(range(self.layout.count())):
            self.layout.itemAt(i).widget().setParent(None)


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



async def c_gui(config_dir: Path, output_dir: Path):
    config_manager = _create_config_manager(config_dir, output_dir)
    app = QApplication(sys.argv)

    window = MainWindow(config_manager)
    window.show()

    app.exec()
