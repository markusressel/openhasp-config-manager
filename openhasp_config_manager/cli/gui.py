import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QVBoxLayout

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.manager import ConfigManager


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
        self.screen_layout = QVBoxLayout()
        container = QWidget()
        container.setLayout(self.screen_layout)
        self.setCentralWidget(container)

    def load_plates(self):
        self.devices = self.config_manager.analyze()

        # add buttons for each device
        for device in sorted(self.devices, key=lambda x: x.name):
            button = QPushButton(device.name)
            button.clicked.connect(lambda _, d=device: self.device_label_clicked(d))
            self.screen_layout.addWidget(button)

    def device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")


async def c_gui(config_dir: Path, output_dir: Path):
    config_manager = _create_config_manager(config_dir, output_dir)
    app = QApplication(sys.argv)

    window = MainWindow(config_manager)
    window.show()

    app.exec()
