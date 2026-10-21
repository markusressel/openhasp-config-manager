"""
Builds the `Device` of a plate without an openhasp-configs directory (README §4.1): connection settings from the
controller's section in haad.yaml, everything else from the `PlateConfig`.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.openhasp_client.model.configuration.debug_config import DebugConfig
from openhasp_config_manager.openhasp_client.model.configuration.device_config import DeviceConfig
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.configuration.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.configuration.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.configuration.mqtt_config import MqttConfig, MqttTopicConfig
from openhasp_config_manager.openhasp_client.model.configuration.screen_config import ScreenConfig
from openhasp_config_manager.openhasp_client.model.configuration.telnet_config import TelnetConfig
from openhasp_config_manager.openhasp_client.model.configuration.wifi_config import WifiConfig
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


@dataclass(frozen=True)
class MqttBroker:
    host: str
    port: int
    user: Optional[str]
    password: Optional[str]


def build_device(name: str, settings: Mapping[str, Any], plate_config, default_broker: MqttBroker) -> Device:
    """
    The in-memory `Device` that OpenHaspClient expects.

    :param name: the plate's name (its haad registry name)
    :param settings: the controller's section in haad.yaml: `host`, `mqtt_name`, `http_user`, `http_password`, and optionally
        `mqtt: {host, port, user, password}` (default: `default_broker`)
    :param plate_config: the PlateConfig; its `screen` is required
    :param default_broker: haad's own MQTT broker
    """
    missing = [key for key in ["host", "mqtt_name", "http_user", "http_password"] if key not in settings]
    if missing:
        raise KeyError(f"Missing settings of plate '{name}' in haad.yaml (controllers.{name}): {', '.join(missing)}")
    if plate_config.screen is None:
        raise ValueError(f"Plate '{name}' has no config_dir: its PlateConfig needs a screen=Screen(width, height)")

    mqtt = settings.get("mqtt", {})
    gui = plate_config.gui
    config = Config(
        openhasp_config_manager=OpenhaspConfigManagerConfig(
            device=DeviceConfig(
                ip=settings["host"],
                screen=ScreenConfig(width=plate_config.screen.width, height=plate_config.screen.height),
            ),
        ),
        # not used by haad: the plate keeps its own wifi and hasp settings
        wifi=WifiConfig(ssid="", password=""),
        mqtt=MqttConfig(
            name=settings["mqtt_name"],
            host=mqtt.get("host", default_broker.host),
            port=mqtt.get("port", default_broker.port),
            user=mqtt.get("user", default_broker.user),
            password=mqtt.get("password", default_broker.password),
            topic=MqttTopicConfig(node="hasp/%hostname%/%topic%", group="hasp/plates/%topic%", broadcast="hasp/broadcast/%topic%",
                                  hass="homeassistant/status"),
        ),
        http=HttpConfig(port=80, user=settings["http_user"], password=settings["http_password"]),
        gui=GuiConfig(idle1=gui.idle1, idle2=gui.idle2) if gui is not None else GuiConfig(),
        hasp=HaspConfig(startpage=1, startdim=255, theme=0, color1="", color2="", font="", pages=""),
        debug=DebugConfig(ansi=0, baud=115200, tele=300, host="", port=541, proto=0, log=0),
        telnet=TelnetConfig(enable=0, port=23),
    )
    return Device(name=name, path=Path(), config=config, jsonl=[], cmd=[], images=[], fonts=[], output_dir=Path())


def create_client(device: Device) -> OpenHaspClient:
    return OpenHaspClient(device=device)
