from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class WebserverConfig:
    website: str
    user: str
    password: str


@dataclass
class Component:
    name: str
    path: Path


@dataclass
class Device:
    name: str
    path: Path
    webserver: WebserverConfig
    components: List[Component]
    output_dir: Path
