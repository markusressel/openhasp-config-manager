from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ScreenConfig:
    width: int
    height: int


@dataclass
class DeviceConfig:
    ip: str
    screen: ScreenConfig


@dataclass
class WebsiteConfig:
    website: str


@dataclass
class OpenhaspConfigManagerConfig:
    device: DeviceConfig


@dataclass
class MqttConfig:
    name: str
    group: str
    host: str
    port: int
    user: str
    password: Optional[str]


@dataclass
class HttpConfig:
    port: int
    user: str
    password: Optional[str]


@dataclass
class Config:
    openhasp_config_manager: OpenhaspConfigManagerConfig
    mqtt: Optional[MqttConfig]
    http: Optional[HttpConfig]


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
