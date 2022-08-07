from dataclasses import dataclass
from pathlib import Path
from typing import List


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
    password: str


@dataclass
class HttpConfig:
    port: int
    user: str
    password: str


@dataclass
class GuiConfig:
    idle1: int
    idle2: int
    bckl: int
    bcklinv: int
    rotate: int
    cursor: int
    invert: int
    calibration: List[int]


@dataclass
class HaspConfig:
    startpage: int
    startdim: int
    theme: int
    color1: str
    color2: str
    font: str
    pages: str


@dataclass
class Config:
    openhasp_config_manager: OpenhaspConfigManagerConfig
    mqtt: MqttConfig
    http: HttpConfig
    gui: GuiConfig
    hasp: HaspConfig


@dataclass
class Component:
    name: str
    type: str
    path: Path
    content: str


@dataclass
class Device:
    name: str
    path: Path
    config: Config
    components: List[Component]
    output_dir: Path
