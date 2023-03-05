from dataclasses import dataclass

from openhasp_config_manager.openhasp_client.model.device_config import DeviceConfig


@dataclass
class OpenhaspConfigManagerConfig:
    device: DeviceConfig
