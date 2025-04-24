from dataclasses import dataclass

from openhasp_config_manager.openhasp_client.model.configuration.debug_config import DebugConfig
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.configuration.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.configuration.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.configuration.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.model.configuration.telnet_config import TelnetConfig
from openhasp_config_manager.openhasp_client.model.configuration.wifi_config import WifiConfig
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig


@dataclass
class Config:
    openhasp_config_manager: OpenhaspConfigManagerConfig
    wifi: WifiConfig
    mqtt: MqttConfig
    http: HttpConfig
    gui: GuiConfig
    hasp: HaspConfig
    debug: DebugConfig
    telnet: TelnetConfig
