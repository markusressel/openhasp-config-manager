from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device


class OpenHaspDevicePagesData:
    def __init__(
        self,
        device: Device,
        name: str,
        jsonl_components: List[JsonlComponent],
        part_includers: Optional[Dict[Path, List[Tuple[str, Path]]]] = None,
    ):
        """:param part_includers: the parts -> (device, file) of every file that includes them (see `LoadedDevice`)"""
        self.device = device
        self.name = name
        self.jsonl_components = jsonl_components
        self.part_includers = part_includers or {}
