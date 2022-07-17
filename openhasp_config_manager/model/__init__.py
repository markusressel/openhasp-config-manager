from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class MqttConfig:
    name: str
    group: str
    host: str
    port: int
    user: str
    password: str


@dataclass
class HttpConfig:
    website: str
    port: int
    user: str
    password: str


@dataclass
class Config:
    mqtt: MqttConfig
    http: HttpConfig


@dataclass
class Component:
    name: str
    path: Path


@dataclass
class Device:
    name: str
    path: Path
    config: Config
    components: List[Component]
    output_dir: Path
