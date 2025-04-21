from dataclasses import dataclass
from pathlib import Path
from typing import List

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent, CmdComponent, \
    ImageComponent, FontComponent
from openhasp_config_manager.openhasp_client.model.configuration.config import Config


@dataclass
class Device:
    name: str
    path: Path
    config: Config
    jsonl: List[JsonlComponent]
    cmd: List[CmdComponent]
    images: List[ImageComponent]
    fonts: List[FontComponent]
    output_dir: Path
