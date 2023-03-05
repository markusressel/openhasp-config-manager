from dataclasses import dataclass
from pathlib import Path
from typing import List

from openhasp_config_manager.openhasp_client.model.component import Component
from openhasp_config_manager.openhasp_client.model.config import Config


@dataclass
class Device:
    name: str
    path: Path
    config: Config
    components: List[Component]
    output_dir: Path
