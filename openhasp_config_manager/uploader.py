from pathlib import Path
from typing import List

from openhasp_config_manager.model import Device
from openhasp_config_manager.openhasp import OpenHaspClient


class ConfigUploader:

    def __init__(self, output_root: Path):
        self.api_client = OpenHaspClient()
        self.output_root = output_root

    def upload(self, devices: List[Device]):
        for device in devices:
            print(f"Uploading files to device '{device.name}'...")
            self._upload_files(self.output_root, device)

        # TODO: naming clashes can still happen and there is no warning about them

    def _upload_files(self, output_root: Path, device: Device):
        common_dir = Path(output_root, "common")
        for file in common_dir.iterdir():
            print(f"Uploading '{file.name}'...")
            content = file.read_text()
            self.api_client.upload_file(device, file.name, content)

        for file in device.output_dir.iterdir():
            print(f"Uploading '{file.name}'...")
            content = file.read_text()
            self.api_client.upload_file(device, file.name, content)
