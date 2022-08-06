from pathlib import Path
from typing import List, Dict

from openhasp_config_manager.model import Device
from openhasp_config_manager.openhasp import OpenHaspClient


class ConfigUploader:

    def __init__(self, output_root: Path):
        self._api_client = OpenHaspClient()
        self._output_root = output_root
        self._cache_dir = Path(self._output_root, ".cache")

    def upload(self, device: Device):
        self._upload_files(device)
        self._update_config(device)

    def upload_all(self, devices: List[Device]):
        for device in devices:
            self.upload(device)

    def _upload_files(self, device: Device):
        file_map: Dict[str, bool] = {}

        for file in device.output_dir.iterdir():
            print(f"Preparing '{file.name}' for upload...")

            if file.name in file_map:
                raise ValueError(f"Naming clash for file: {file.name}")

            content = file.read_text()

            new_checksum = self._compare_checksum(file, content)
            if new_checksum is not None:
                file_map[file.name] = True
                try:
                    self._api_client.upload_file(device, file.name, content)
                    checksum_file = self._get_checksum_file(file)
                    checksum_file.parent.mkdir(parents=True, exist_ok=True)
                    checksum_file.write_text(new_checksum)
                except Exception as ex:
                    print(f"Error uploading file '{file.name}': {ex}")
            else:
                print(f"Skipping {file} because it hasn't changed.")

    def _compare_checksum(self, file: Path, content: str) -> str | None:
        """
        Checks if the checksum for the given file has changed since it was last uploaded.
        :param file: the path of the file to check
        :param content: the content of the new file
        :return: new checksum if the checksum changed, None otherwise
        """
        import hashlib
        new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        checksum_file = self._get_checksum_file(file)
        if not checksum_file.exists():
            changed = True
        else:
            old_hash = checksum_file.read_text().strip()
            changed = old_hash != new_hash

        if changed:
            return new_hash
        else:
            return None

    def _get_checksum_file(self, file: Path) -> Path:
        return Path(
            self._cache_dir,
            *file.relative_to(self._output_root).parts[:-1],
            file.name + ".md5"
        )

    def _update_config(self, device: Device):
        self._api_client.set_mqtt_config(device, device.config.mqtt)
        self._api_client.set_http_config(device, device.config.http)
        self._api_client.set_gui_config(device, device.config.gui)
