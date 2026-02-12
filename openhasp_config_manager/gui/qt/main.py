from typing import Optional, List, Dict

from PyQt6.QtWidgets import QWidget, QMainWindow

from openhasp_config_manager.gui.domain.plate_state_holder import PlateStateHolder
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.widgets.device_controls import DeviceControlsWidget
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget, OpenHaspDevicePagesData
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import CmdComponent
from openhasp_config_manager.openhasp_client.model.device import Device


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.devices: List[Device] = []
        self.plate_state_holders: Dict[Device, PlateStateHolder] = {}
        self.device: Optional[Device] = None

        self.setWindowTitle("openhasp-config-manager")

        self.create_basic_layout()
        self.load_plates()

    def create_basic_layout(self):
        self.container = QWidget()
        self.layout = UiComponents.create_column()
        self.container.setLayout(self.layout)

        self.device_list_widget = DeviceListWidget()
        self.device_list_widget.deviceSelected.connect(self.on_device_selected)
        self.layout.addWidget(self.device_list_widget)

        self.device_layout = UiComponents.create_row()
        self.layout.addLayout(self.device_layout)

        self.device_control_widget = DeviceControlsWidget()
        self.device_layout.addWidget(self.device_control_widget)
        self.device_control_widget.setVisible(False)

        self.page_layout_editor_widget = PageLayoutEditorWidget(
            config_manager=self.config_manager
        )
        self.device_layout.addWidget(self.page_layout_editor_widget)
        self.page_layout_editor_widget.setVisible(False)

        self.setCentralWidget(self.container)

    def load_plates(self):
        self.devices = self.config_manager.analyze()

        # create state holders for each device
        for device in self.devices:
            plate_state_holder = PlateStateHolder(device=device)
            self.plate_state_holders[device] = plate_state_holder

        self.device_list_widget.set_devices(self.devices)

    def on_device_selected(self, device: Device):
        # reload devices to reflect any changes that happened on disk
        self.load_plates()

        find_device = next((d for d in self.devices if d.name == device.name), None)
        if find_device:
            self.select_device(find_device)

    def select_device(self, device: Device):
        self.device = device

        plate_state_holder = self.plate_state_holders[device]

        self.device_control_widget.set_device(self.device)
        self.device_control_widget.setVisible(True)
        self.page_layout_editor_widget.setVisible(True)

        # setup sample page layout editor for testing
        # device_processor = self.config_manager.create_device_processor(device)
        # device_validator = self.config_manager.create_device_validator(device)
        self.relevant_components = self.config_manager.find_relevant_components(device)
        boot_cmd_component: CmdComponent = next(
            filter(lambda x: x.name == "boot.cmd", self.relevant_components), None)
        self.select_cmd_component(plate_state_holder, boot_cmd_component)

    def select_cmd_component(self, plate_state_holder: PlateStateHolder, cmd_component: CmdComponent):
        """
        Selects the given cmd component.
        :param plate_state_holder: The plate state holder for the device.
        :param cmd_component: The cmd component to select.
        """
        ordered_device_jsonl_components = self.config_manager.determine_device_jsonl_component_order_for_cmd(
            device=plate_state_holder.device,
            cmd_component=cmd_component,
        )

        self.page_layout_editor_widget.set_data(
            state_holder=plate_state_holder,
            device_pages_data=OpenHaspDevicePagesData(
                device=plate_state_holder.device,
                name=cmd_component.name,
                jsonl_components=ordered_device_jsonl_components
            )
        )
