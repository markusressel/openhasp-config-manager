from typing import List

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import JsonlComponent, CmdComponent
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
        self.select_cmd_component(boot_cmd_component)

    def select_cmd_component(self, cmd_component: CmdComponent):
        """
        Selects the given cmd component in the file browser widget.
        :param cmd_component: The cmd component to select.
        """
        device_cmd_components: List[CmdComponent] = list(
            filter(lambda x: isinstance(x, CmdComponent), self.relevant_components)
        )
        device_jsonl_components: List[JsonlComponent] = list(
            filter(lambda x: isinstance(x, JsonlComponent), self.relevant_components)
        )

        ordered_device_jsonl_components = self._determine_device_jsonl_component_order_for_cmd(
            cmd_component,
            device_cmd_components,
            device_jsonl_components
        )

        self.page_layout_editor_widget.set_data(
            OpenHaspDevicePagesData(
                device=self.device,
                name=cmd_component.name,
                jsonl_components=ordered_device_jsonl_components
            )
        )

    def _determine_device_jsonl_component_order_for_cmd(
        self, cmd_component: CmdComponent,
        device_cmd_components: List[CmdComponent],
        device_jsonl_components: List[JsonlComponent]) -> List[JsonlComponent]:
        """
        Determines the order of the jsonl components based on the order of their reference in cmd components.

        :param cmd_component: The cmd component to analyze.
        :param device_cmd_components: The list of cmd components to check for references.
        :param device_jsonl_components: The list of jsonl components to order.
        :return: The ordered list of jsonl components.
        """
        jsonl_components = []

        for cmd in cmd_component.commands:
            if cmd.endswith(".jsonl"):
                jsonl_component_name = cmd.split("/")[-1]
                jsonl_component = next(
                    filter(lambda x: x.name == jsonl_component_name, device_jsonl_components), None
                )
                if jsonl_component is None:
                    raise AssertionError(f"Component {jsonl_component_name} not found in device jsonl components")
                jsonl_components.append(jsonl_component)
            elif cmd.endswith(".cmd"):
                cmd_component_name = cmd.split("/")[-1]
                cmd_component = next(
                    filter(lambda x: x.name == cmd_component_name, device_cmd_components), None
                )
                if cmd_component is None:
                    raise AssertionError(f"Component {cmd_component_name} not found in device cmd components")
                jsonl_components.extend(
                    self._determine_device_jsonl_component_order_for_cmd(
                        cmd_component,
                        device_cmd_components,
                        device_jsonl_components
                    )
                )

        return jsonl_components
