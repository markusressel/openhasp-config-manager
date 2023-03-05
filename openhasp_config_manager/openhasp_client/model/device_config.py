from dataclasses import dataclass

from openhasp_config_manager.openhasp_client.model.screen_config import ScreenConfig


@dataclass
class DeviceConfig:
    ip: str
    screen: ScreenConfig
