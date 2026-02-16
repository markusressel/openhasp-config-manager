from pathlib import Path

import pytest

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
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig


def _find_test_folder() -> Path:
    p = Path("./")

    if p.absolute().parts[-1] == "tests":
        return p
    else:
        import glob

        while str(p.absolute()) != "/":
            files = glob.glob(str(Path(p)) + "/**/tests", recursive=True)
            if len(files) > 0:
                return Path(files[0]).absolute()
            else:
                p = p.parent.absolute()

    raise AssertionError("test folder not found")


@pytest.mark.usefixtures("tmp_path")
class TestBase:
    _test_folder = _find_test_folder()
    cfg_root = Path(_test_folder, Path("_test_cfg_root"))

    default_config = Config(
        openhasp_config_manager=OpenhaspConfigManagerConfig(
            device=DeviceConfig(
                ip="192.168.1.10",
                screen=ScreenConfig(
                    width=320,
                    height=480,
                ),
            )
        ),
        wifi=WifiConfig(
            ssid="ssid",
            password="password",
        ),
        mqtt=MqttConfig(
            name="name",
            topic=MqttTopicConfig(
                node="node",
                group="group",
                broadcast="broadcast",
                hass="hass",
            ),
            host="mqtt.host",
            port=1883,
            user="user",
            password="password",
        ),
        http=HttpConfig(
            port=80,
            user="user",
            password="password",
        ),
        gui=GuiConfig(
            idle1=10,
            idle2=60,
            bckl=32,
            bcklinv=0,
            rotate=1,
            cursor=0,
            invert=0,
            calibration=[0, 65535, 0, 65535, 0],
        ),
        hasp=HaspConfig(
            startpage=1,
            startdim=255,
            theme=2,
            color1="#000000",
            color2="#000000",
            font="",
            pages="/pages_home.jsonl",
        ),
        debug=DebugConfig(
            ansi=1,
            baud=115200,
            tele=300,
            host="",
            port=541,
            proto=0,
            log=0,
        ),
        telnet=TelnetConfig(
            enable=1,
            port=23,
        ),
    )
