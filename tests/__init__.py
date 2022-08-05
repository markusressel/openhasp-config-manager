from pathlib import Path
from unittest import TestCase

from openhasp_config_manager.model import Config, OpenhaspConfigManagerConfig, DeviceConfig, ScreenConfig


def _find_test_folder() -> Path:
    p = Path("./")
    if p.absolute().parts[-1] == "tests":
        return p
    else:
        import glob
        files = glob.glob(str(Path(p)) + '/**/tests', recursive=True)
        return Path(files[0]).absolute()


class TestBase(TestCase):
    _test_folder = _find_test_folder()
    cfg_root = Path(_test_folder, Path("test_cfg_root"))
    output = Path(_test_folder, "test_output")

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
