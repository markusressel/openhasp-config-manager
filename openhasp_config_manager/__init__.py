from pathlib import Path

from openhasp_config_manager.processor import ConfigProcessor
from openhasp_config_manager.uploader import ConfigUploader

if __name__ == '__main__':
    cfg_dir_root = Path("../openhasp-configs")
    output_root = Path("../output")

    processor = ConfigProcessor(cfg_dir_root, output_root)
    devices = processor.process()

    uploader = ConfigUploader(output_root)
    uploader.upload(devices)
