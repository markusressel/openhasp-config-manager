import difflib
from pathlib import Path

from openhasp_config_manager import util
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.util import print_diff_to_console, info, warn


class ConfigUploader:

    def __init__(self, output_root: Path, openhasp_client: OpenHaspClient):
        self._api_client = openhasp_client
        self._output_root = output_root
        self._cache_dir = Path(self._output_root, ".cache")

    def upload(self, device: Device, purge: bool = False, print_diff: bool = False) -> bool:
        """
        Uploads configuration files and config properties to a device.
        :param device: The device to upload to.
        :param purge: If True, removes files from the device, which are not present in the generated output.
        :param print_diff: If true, a diff will be printed to the console for each file that has changed.
        :return: True if any files have changed, false otherwise.
        """
        result = False

        if purge:
            result |= self.cleanup_device(device)

        result |= self._upload_files(device, print_diff)
        result |= self._update_config(device)
        return result

    def _upload_files(self, device: Device, print_diff: bool) -> bool:
        existing_files = self._api_client.get_files()

        result = False

        for file in device.output_dir.iterdir():
            info(f"Preparing '{file.name}' for upload...")

            if file.suffix in [".cmd", ".jsonl"]:
                result |= self._upload_text_file(device, print_diff, file, existing_files)
            else:
                result |= self._upload_binary_file(device, print_diff, file, existing_files)

        return result

    def _upload_text_file(self, device, print_diff, file, existing_files) -> bool:
        result = False

        content = file.read_text()
        if len(content) <= 0:
            warn(f"File is empty, skipping upload: {file}")
            return result

        # check if the checksum of the file has changed on the device
        file_content_on_device = ""
        if file.name in existing_files:
            file_content_on_device = self._api_client.get_file_content(file.name).decode("utf-8")
            device_file_content_checksum = util.calculate_checksum(file_content_on_device.encode("utf-8"))
        else:
            device_file_content_checksum = None

        new_checksum = self._check_if_checksum_will_change(
            file=file,
            original_checksum=device_file_content_checksum,
            new_content=content.encode("utf-8")
        )

        if new_checksum is not None:
            result = True
            if print_diff:
                diff_output = self._calculate_diff(
                    file_name=file.name,
                    string1=file_content_on_device,
                    string2=content
                )
                print_diff_to_console(diff_output)
            try:
                self._api_client.upload_file(file.name, content.encode("utf-8"))
                checksum_file = self._get_checksum_file(file)
                checksum_file.parent.mkdir(parents=True, exist_ok=True)
                checksum_file.write_text(new_checksum)
            except Exception as ex:
                raise Exception(f"Error uploading file '{file.name}' to '{device.name}': {ex}")
        else:
            info(f"Skipping {file} because it hasn't changed.")

        return result

    def _upload_binary_file(self, device, print_diff, file, existing_files) -> bool:
        result = False

        content = file.read_bytes()
        if len(content) <= 0:
            warn(f"File is empty, skipping upload: {file}")
            return result

        # check if the checksum of the file has changed on the device
        file_content_on_device = b""
        if file.name in existing_files:
            file_content_on_device: bytes = self._api_client.get_file_content(file.name)
            device_file_content_checksum = util.calculate_checksum(file_content_on_device)
        else:
            device_file_content_checksum = None

        new_checksum = self._check_if_checksum_will_change(
            file=file,
            original_checksum=device_file_content_checksum,
            new_content=content
        )

        if new_checksum is not None:
            result = True
            if print_diff:
                info(f"Binary file '{file.name}' has changed ({device_file_content_checksum} -> {new_checksum})")
            try:
                self._api_client.upload_file(file.name, content)
                checksum_file = self._get_checksum_file(file)
                checksum_file.parent.mkdir(parents=True, exist_ok=True)
                checksum_file.write_text(new_checksum)
            except Exception as ex:
                raise Exception(f"Error uploading file '{file.name}' to '{device.name}': {ex}")
        else:
            info(f"Skipping {file} because it hasn't changed.")

        return result

    def cleanup_device(self, device: Device) -> bool:
        """
        Delete files from the device, which are not present in the currently generated output
        :param device: the target device
        :return: True if any files have been deleted, false otherwise
        """
        result = False

        file_names = ["config.json"]
        for file in device.output_dir.iterdir():
            file_names.append(file.name)

        # cleanup files which are on the device, but not present in the generated output
        files_on_device = self._api_client.get_files()
        for f in files_on_device:
            if f not in file_names:
                result = True
                info(f"Deleting file '{f}' from device '{device.name}'")
                self._api_client.delete_file(f)
        return result

    def _check_if_checksum_will_change(self, file: Path, original_checksum: str, new_content: bytes) -> str | None:
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
        config_has_changed = False

        current_mqtt_config = self._api_client.get_mqtt_config()
        if current_mqtt_config == device.config.mqtt:
            info("MQTT config has not changed")
        else:
            info("Updating MQTT config...")
            self._api_client.set_mqtt_config(device.config.mqtt)
            config_has_changed = True

        current_http_config = self._api_client.get_http_config()
        if current_http_config == device.config.http:
            info("HTTP config has not changed")
        else:
            info("Updating HTTP config...")
            self._api_client.set_http_config(device.config.http)
            config_has_changed = True

        current_gui_config = self._api_client.get_gui_config()
        if current_gui_config == device.config.gui:
            info("GUI config has not changed")
        else:
            info("Updating GUI config...")
            self._api_client.set_gui_config(device.config.gui)
            config_has_changed = True

        return config_has_changed

    @staticmethod
    def _calculate_diff(file_name: str, string1: str, string2: str) -> str:
        diff = difflib.unified_diff(
            string1.splitlines(),
            string2.splitlines(),
            lineterm="\n",
            fromfile=f"${file_name}",
            tofile=f"${file_name}"
        )

        return "\n".join(list(diff))
