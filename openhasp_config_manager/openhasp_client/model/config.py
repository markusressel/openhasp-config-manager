from dataclasses import dataclass

from openhasp_config_manager.openhasp_client.model.debug_config import DebugConfig
from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig
from openhasp_config_manager.openhasp_client.model.telnet_config import TelnetConfig


@dataclass
class Config:
    openhasp_config_manager: OpenhaspConfigManagerConfig
    mqtt: MqttConfig
    http: HttpConfig
    gui: GuiConfig
    hasp: HaspConfig
    debug: DebugConfig
    telnet: TelnetConfig
