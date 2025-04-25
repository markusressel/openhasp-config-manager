from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import CmdComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.device_list import DeviceListWidget
from openhasp_config_manager.ui.qt.file_browser import FileBrowserWidget
from openhasp_config_manager.ui.qt.page_layout_editor import PageLayoutEditorWidget, OpenHaspDevicePagesData


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
        self.device_list_widget.deviceSelected.connect(self.on_device_selected)
        self.layout.addWidget(self.device_list_widget)

        self.file_browser_widget = FileBrowserWidget(self.config_manager.cfg_root)
        self.layout.addWidget(self.file_browser_widget)

        self.page_layout_editor_widget = PageLayoutEditorWidget(
            config_manager=self.config_manager
        )
        self.layout.addWidget(self.page_layout_editor_widget)

        self.setCentralWidget(self.container)

    def load_plates(self):
        self.devices = self.config_manager.analyze()
        self.device_list_widget.set_devices(self.devices)

    def on_device_selected(self, device: Device):
        self.select_device(device)

    def select_device(self, device):
        self.device = device

        # setup sample page layout editor for testing
        # device_processor = self.config_manager.create_device_processor(device)
        # device_validator = self.config_manager.create_device_validator(device)
        self.relevant_components = self.config_manager.find_relevant_components(device)
        boot_cmd_component: CmdComponent = next(
            filter(lambda x: x.name == "boot.cmd", self.relevant_components), None)
        self.select_cmd_component(device, boot_cmd_component)

    def select_cmd_component(self, device: Device, cmd_component: CmdComponent):
        """
        Selects the given cmd component in the file browser widget.
        :param device: The device to select the cmd component for.
        :param cmd_component: The cmd component to select.
        """
        ordered_device_jsonl_components = self.config_manager.determine_device_jsonl_component_order_for_cmd(
            device=device,
            cmd_component=cmd_component,
        )

        self.page_layout_editor_widget.set_data(
            OpenHaspDevicePagesData(
                device=self.device,
                name=cmd_component.name,
                jsonl_components=ordered_device_jsonl_components
            )
        )
