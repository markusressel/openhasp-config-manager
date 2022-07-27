from pathlib import Path
from unittest import TestCase

from openhasp_config_manager.model import Config, OpenhaspConfigManagerConfig, DeviceConfig, ScreenConfig


class TestBase(TestCase):
    cfg_root = Path("./test_cfg_root")
    output = Path("./test_output")

    default_config = Config(
        openhasp_config_manager=OpenhaspConfigManagerConfig(
            device=DeviceConfig(
                ip="192.168.1.10",
                screen=ScreenConfig(
                    width=320,
                    height=480,
                )
            )
        ),
        mqtt=None,
        http=None,
        gui=None,
        hasp=None,
    )
