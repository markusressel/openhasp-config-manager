from dataclasses import dataclass

from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig


@dataclass
class Config:
    openhasp_config_manager: OpenhaspConfigManagerConfig
    mqtt: MqttConfig
    http: HttpConfig
    gui: GuiConfig
    hasp: HaspConfig
