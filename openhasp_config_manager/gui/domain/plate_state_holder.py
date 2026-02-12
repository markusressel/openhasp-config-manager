from dataclasses import dataclass
from typing import List, OrderedDict, Dict

from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.openhasp_client.model.device import Device


@dataclass
class PlateState:
    name: str
    widgets: list
    jsonl_component_objects: OrderedDict[str, List[Dict]]


class PlateStateHolder:
    def __init__(self, device: Device):
        self.device = device
        self.plate_state = PlateState(
            name=device.name,
            widgets=[],
            jsonl_component_objects=OrderedDict()
        )
        self.device_pages_data: OpenHaspDevicePagesData = None

    def set_state(self, plate_state: PlateState):
        self.plate_state = plate_state

    def add_widget(self, widget: EditableWidget):
        self.plate_state.widgets.append(widget)

    def remove_widget(self, widget: EditableWidget):
        self.plate_state.widgets.remove(widget)

    def is_loaded(self) -> bool:
        return len(self.plate_state.widgets) > 0

    def set_jsonl_component_objects(self, jsonl_component_objects: OrderedDict[str, List[Dict]]):
        self.plate_state.jsonl_component_objects = jsonl_component_objects
