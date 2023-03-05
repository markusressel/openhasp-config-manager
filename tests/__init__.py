from pathlib import Path

import pytest

from openhasp_config_manager.openhasp_client.model.config import Config
from openhasp_config_manager.openhasp_client.model.device_config import DeviceConfig
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig
from openhasp_config_manager.openhasp_client.model.screen_config import ScreenConfig


def _find_test_folder() -> Path:
    p = Path("./")

    if p.absolute().parts[-1] == "tests":
        return p
    else:
        import glob
        while str(p.absolute()) != "/":
            files = glob.glob(str(Path(p)) + '/**/tests', recursive=True)
            if len(files) > 0:
                return Path(files[0]).absolute()
            else:
                p = p.parent.absolute()

    raise AssertionError("test folder not found")


@pytest.mark.usefixtures('tmp_path')
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
                )
            )
        ),
        mqtt=None,
        http=None,
        gui=None,
        hasp=None,
    )
