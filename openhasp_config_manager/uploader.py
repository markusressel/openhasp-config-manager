from pathlib import Path

from openhasp_config_manager import util
from openhasp_config_manager.model import Device
from openhasp_config_manager.openhasp import OpenHaspClient


class ConfigUploader:

    def __init__(self, output_root: Path):
        self._api_client = OpenHaspClient()
        self._output_root = output_root
        self._cache_dir = Path(self._output_root, ".cache")

    def upload(self, device: Device, purge: bool = False):
        if purge:
            self.cleanup_device(device)
        self._upload_files(device)
        self._update_config(device)

    def _upload_files(self, device: Device):
        existing_files = self._api_client.get_files(device)

        for file in device.output_dir.iterdir():
            print(f"Preparing '{file.name}' for upload...")

            content = file.read_text()

            # check if the checksum of the file has changed on the device
            if file.name in existing_files:
                file_content_on_device = self._api_client.get_file_content(device, file.name)
                device_file_content_checksum = util.calculate_checksum(file_content_on_device)
            else:
                device_file_content_checksum = None

            new_checksum = self._check_if_checksum_will_change(
                file=file,
                original_checksum=device_file_content_checksum,
                new_content=content
            )

            if new_checksum is not None:
                try:
                    self._api_client.upload_file(device, file.name, content)
                    checksum_file = self._get_checksum_file(file)
                    checksum_file.parent.mkdir(parents=True, exist_ok=True)
                    checksum_file.write_text(new_checksum)
                except Exception as ex:
                    print(f"Error uploading file '{file.name}' to '{device.name}': {ex}")
            else:
                print(f"Skipping {file} because it hasn't changed.")

    def cleanup_device(self, device: Device):
        """
        Delete files from the device, which are not present in the currently generated output
        :param device: the target device
        """
        file_names = ["config.json"]
        for file in device.output_dir.iterdir():
            file_names.append(file.name)

        # cleanup files which are on the device, but not present in the generated output
        files_on_device = self._api_client.get_files(device)
        for f in files_on_device:
            if f not in file_names:
                print(f"Deleting file '{f}' from device '{device.name}'")
                self._api_client.delete_file(device, f)

    def _check_if_checksum_will_change(self, file: Path, original_checksum: str, new_content: str) -> str | None:
        """
        Checks if the checksum for the given file has changed since it was last uploaded.
        :param file: the path of the file to check
        :param original_checksum: expected checksum of the original content
        :param new_content: the content of the new file
        :return: new checksum if the checksum changed, None otherwise
        """
        changed = False

        new_content_checksum = util.calculate_checksum(new_content)
        checksum_file = self._get_checksum_file(file)
        if not checksum_file.exists():
            changed = True
        else:
            old_hash = checksum_file.read_text().strip()
            if old_hash != original_checksum or old_hash != new_content_checksum:
                changed = True

        if changed:
            return new_content_checksum
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
