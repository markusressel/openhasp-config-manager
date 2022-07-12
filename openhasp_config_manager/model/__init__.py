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
    index: int
    path: Path


@dataclass
class Page:
    name: str
    index: int
    path: Path
    components: List[Component]


@dataclass
class Device:
    name: str
    path: Path
    webserver: WebserverConfig
    pages: List[Page]
    output_dir: Path
