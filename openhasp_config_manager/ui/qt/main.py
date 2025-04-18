from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.ui.qt.device_list import DeviceListWidget
from openhasp_config_manager.ui.qt.file_browser import FileBrowserWidget
from openhasp_config_manager.ui.qt.page_layout_editor import PageLayoutEditorWidget


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager

        self.setWindowTitle("openhasp-config-manager")

        self.create_basic_layout()
        self.load_plates()

    def create_basic_layout(self):
        self.container = QWidget()
        self.layout = QVBoxLayout()
        self.container.setLayout(self.layout)

        self.device_list_widget = DeviceListWidget(devices=[])
        self.layout.addWidget(self.device_list_widget)

        self.file_browser_widget = FileBrowserWidget(self.config_manager.cfg_root)
        self.layout.addWidget(self.file_browser_widget)

        self.page_layout_editor_widget = PageLayoutEditorWidget()

        self.setCentralWidget(self.container)

    def load_plates(self):
        self.devices = self.config_manager.analyze()
        self.device_list_widget.set_devices(self.devices)
