from pathlib import Path

from openhasp_config_manager import ConfigProcessor


def test_processor():
    cfg_root = Path("./test_cfg_root")
    output = Path("./test_output")

    processor = ConfigProcessor(cfg_root, output)

    devices = processor.analyze()
    processor.process(devices)
