from typing import List

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device


class OpenHaspDevicePagesData:
    def __init__(self, device: Device, name: str, jsonl_components: List[JsonlComponent]):
        self.device = device
        self.name = name
        self.jsonl_components = jsonl_components
