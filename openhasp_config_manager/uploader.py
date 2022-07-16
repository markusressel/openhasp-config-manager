from pathlib import Path
from typing import List, Dict

from openhasp_config_manager.model import Device
from openhasp_config_manager.openhasp import OpenHaspClient


class ConfigUploader:

    def __init__(self, output_root: Path):
        self.api_client = OpenHaspClient()
        self.output_root = output_root
        self._cache_dir = Path(self.output_root, ".cache")

    def upload(self, devices: List[Device]):
        for device in devices:
            print(f"Uploading files to device '{device.name}'...")
            self._upload_files(device)

    def _upload_files(self, device: Device):
        file_map: Dict[str, str] = {}

        for file in device.output_dir.iterdir():
            print(f"Preparing '{file.name}'...")

            if file.name in file_map:
                raise ValueError(f"Naming clash for file: {file.name}")

            content = file.read_text()

            checksum_differs = self._compare_checksum(file, content)
            if checksum_differs:
                file_map[file.name] = content
            else:
                print(f"Skipping {file} because it hasn't changed.")

        self.api_client.upload_files(device, file_map)

    def _compare_checksum(self, file: Path, content: str) -> bool:
        """
        Checks if the checksum for the given file has changed since it was last uploaded.
        :param file: the path of the file to check
        :param content: the content of the new file
        :return: true if the checksum changed, false otherwise
        """
        checksum_file = Path(
            self._cache_dir,
            *file.relative_to(self.output_root).parts[:-1],
            file.name + ".md5"
        )
        import hashlib
        new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        if not checksum_file.exists():
            changed = True
        else:
            old_hash = checksum_file.read_text().strip()
            changed = old_hash != new_hash

        if changed:
            checksum_file.parent.mkdir(parents=True, exist_ok=True)
            checksum_file.write_text(new_hash)

        return changed
