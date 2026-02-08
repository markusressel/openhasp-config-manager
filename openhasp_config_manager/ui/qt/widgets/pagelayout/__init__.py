from typing import List

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.slider import HaspSliderItem
from openhasp_config_manager.ui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem


class OpenHaspDevicePagesData:
    def __init__(self, device: Device, name: str, jsonl_components: List[JsonlComponent]):
        self.device = device
        self.name = name
        self.jsonl_components = jsonl_components
