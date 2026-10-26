import difflib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import List, Optional

from openhasp_config_manager import util
from openhasp_config_manager.console import print_diff_to_console, info, warn
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


# what the plate reads again when its pages are rebuilt (`OpenHaspClient.restore_from_files`). Anything else, like fonts (`.ttf`, and `.bin`
# files, which can be fonts) and the settings of `config.json`, is only loaded when the plate starts.
RELOADABLE_SUFFIXES = (".cmd", ".jsonl", ".png")


# the GUI settings that the plate uses at once when they are sent as the MQTT command `config/gui`, like haad changes the idle timeouts
LIVE_GUI_SETTINGS = ("idle1", "idle2", "bckl", "cursor")


@dataclass
class UploadResult:
    """What an upload changed on the plate."""

    files: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    # settings of `config.json` that the plate only reads at startup: MQTT, HTTP and the GUI settings that are not in `LIVE_GUI_SETTINGS`
    config_changed: bool = False
    # settings that were applied to the running plate, see `LIVE_GUI_SETTINGS`
    settings_applied: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.files or self.deleted or self.config_changed or self.settings_applied)

    @property
    def needs_restart(self) -> bool:
        """Whether the plate has to restart to use the change, instead of rebuilding its pages."""
        return self.config_changed or any(not name.lower().endswith(RELOADABLE_SUFFIXES) for name in self.files + self.deleted)


class ConfigUploader:
    def __init__(self, output_root: Path, openhasp_client: OpenHaspClient):
        self._api_client = openhasp_client
        self._output_root = output_root
        self._cache_dir = Path(self._output_root, ".cache")

    async def upload(self, device: Device, purge: bool = False, print_diff: bool = False) -> bool:
        """
        Uploads configuration files and config properties to a device.
        :param device: The device to upload to.
        :param purge: If True, removes files from the device, which are not present in the generated output.
        :param print_diff: If true, a diff will be printed to the console for each file that has changed.
        :return: True if any files have changed, false otherwise.
        """
        return (await self.upload_changes(device, purge, print_diff)).changed

    async def upload_changes(self, device: Device, purge: bool = False, print_diff: bool = False) -> UploadResult:
        """Like `upload`, but tells what changed, to decide how the plate has to load it."""
        result = UploadResult()

        if purge:
            result.deleted = await self.cleanup_device_files(device)

        result.files = await self._upload_files(device, print_diff)
        await self._update_config(device, result)
        return result

    async def _upload_files(self, device: Device, print_diff: bool) -> List[str]:
        existing_files = await self._api_client.get_files()

        result = []

        for file in device.output_dir.iterdir():
            info(f"Preparing '{file.name}' for upload...")

            if file.suffix in [".cmd", ".jsonl"]:
                uploaded = await self._upload_text_file(device, print_diff, file, existing_files)
            else:
                uploaded = await self._upload_binary_file(device, print_diff, file, existing_files)
            if uploaded:
                result.append(file.name)

        return result

    async def _upload_text_file(self, device, print_diff, file, existing_files) -> bool:
        result = False

        content = file.read_text()
        if len(content) <= 0:
            warn(f"File is empty, skipping upload: {file}")
            return result

        # check if the checksum of the file has changed on the device
        file_content_on_device = ""
        if file.name in existing_files:
            file_content_on_device = (await self._api_client.get_file_content(file.name)).decode("utf-8")
            device_file_content_checksum = util.calculate_checksum(file_content_on_device.encode("utf-8"))
        else:
            device_file_content_checksum = None

        new_checksum = self._check_if_checksum_will_change(
            file=file,
            original_checksum=device_file_content_checksum,
            new_content=content.encode("utf-8"),
        )

        if new_checksum is not None:
            result = True
            if print_diff:
                diff_output = self._calculate_diff(
                    file_name=file.name,
                    string1=file_content_on_device,
                    string2=content,
                )
                print_diff_to_console(diff_output)
            try:
                await self._api_client.upload_file(file.name, content.encode("utf-8"))
                checksum_file = self._get_checksum_file(file)
                checksum_file.parent.mkdir(parents=True, exist_ok=True)
                checksum_file.write_text(new_checksum)
            except Exception as ex:
                raise Exception(f"Error uploading file '{file.name}' to '{device.name}': {ex}")
        else:
            info(f"Skipping {file} because it hasn't changed.")

        return result

    async def _upload_binary_file(self, device, print_diff, file, existing_files) -> bool:
        result = False

        content = file.read_bytes()
        if len(content) <= 0:
            warn(f"File is empty, skipping upload: {file}")
            return result

        # check if the checksum of the file has changed on the device
        file_content_on_device = b""
        if file.name in existing_files:
            file_content_on_device: bytes = await self._api_client.get_file_content(file.name)
            device_file_content_checksum = util.calculate_checksum(file_content_on_device)
        else:
            device_file_content_checksum = None

        new_checksum = self._check_if_checksum_will_change(
            file=file,
            original_checksum=device_file_content_checksum,
            new_content=content,
        )

        if new_checksum is not None:
            result = True
            if print_diff:
                info(f"Binary file '{file.name}' has changed ({device_file_content_checksum} -> {new_checksum})")
            try:
                await self._api_client.upload_file(file.name, content)
                checksum_file = self._get_checksum_file(file)
                checksum_file.parent.mkdir(parents=True, exist_ok=True)
                checksum_file.write_text(new_checksum)
            except Exception as ex:
                raise Exception(f"Error uploading file '{file.name}' to '{device.name}': {ex}")
        else:
            info(f"Skipping {file} because it hasn't changed.")

        return result

    async def cleanup_device(self, device: Device) -> bool:
        """
        Delete files from the device, which are not present in the currently generated output
        :param device: the target device
        :return: True if any files have been deleted, false otherwise
        """
        return bool(await self.cleanup_device_files(device))

    async def cleanup_device_files(self, device: Device) -> List[str]:
        """:return: the names of the files that were deleted from the device, see `cleanup_device`"""
        result = []

        file_names = ["config.json"]
        for file in device.output_dir.iterdir():
            file_names.append(file.name)

        # cleanup files which are on the device, but not present in the generated output
        files_on_device = await self._api_client.get_files()
        for f in files_on_device:
            if f not in file_names:
                result.append(f)
                info(f"Deleting file '{f}' from device '{device.name}'")
                await self._api_client.delete_file(f)
        return result

    def _check_if_checksum_will_change(self, file: Path, original_checksum: str, new_content: bytes) -> Optional[str]:
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
            file.name + ".md5",
        )

    async def _update_config(self, device: Device, result: UploadResult):

        current_mqtt_config = await self._api_client.get_mqtt_config()
        if self._is_up_to_date(device, "mqtt", current_mqtt_config, device.config.mqtt):
            info("MQTT config has not changed")
        else:
            info("Updating MQTT config...")
            await self._api_client.set_mqtt_config(device.config.mqtt)
            self._remember_password(device, "mqtt", device.config.mqtt.password)
            result.config_changed = True

        current_http_config = await self._api_client.get_http_config()
        if self._is_up_to_date(device, "http", current_http_config, device.config.http):
            info("HTTP config has not changed")
        else:
            info("Updating HTTP config...")
            await self._api_client.set_http_config(device.config.http)
            self._remember_password(device, "http", device.config.http.password)
            result.config_changed = True

        current_gui_config = await self._api_client.get_gui_config()
        if current_gui_config == device.config.gui:
            info("GUI config has not changed")
        else:
            info("Updating GUI config...")
            await self._api_client.set_gui_config(device.config.gui)
            changed = {
                f.name: getattr(device.config.gui, f.name)
                for f in fields(device.config.gui)
                if getattr(current_gui_config, f.name) != getattr(device.config.gui, f.name)
            }
            live = {name: value for name, value in changed.items() if name in LIVE_GUI_SETTINGS and value is not None}
            if live:
                await self._api_client.apply_gui_settings(live)
                result.settings_applied = True
            if any(name not in LIVE_GUI_SETTINGS for name in changed):
                result.config_changed = True

    def _password_checksum_file(self, device: Device, section: str) -> Path:
        return Path(self._cache_dir, device.name, f"{section}.password.md5")

    def _remember_password(self, device: Device, section: str, password: str):
        file = self._password_checksum_file(device, section)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(util.calculate_checksum(password.encode("utf-8")))

    def _is_up_to_date(self, device: Device, section: str, current, wanted) -> bool:
        """
        :return: whether the settings on the plate are the wanted ones. The plate doesn't tell its passwords, it returns a mask
            (`********`) instead. So the password is compared with the one that was uploaded last, if it is masked.
        """
        if current == wanted:
            return True
        masked = bool(current.password) and set(current.password) == {"*"}
        if not masked or replace(current, password=wanted.password) != wanted:
            return False
        file = self._password_checksum_file(device, section)
        return file.exists() and file.read_text().strip() == util.calculate_checksum(wanted.password.encode("utf-8"))

    @staticmethod
    def _calculate_diff(file_name: str, string1: str, string2: str) -> str:
        diff = difflib.unified_diff(
            string1.splitlines(),
            string2.splitlines(),
            lineterm="\n",
            fromfile=f"${file_name}",
            tofile=f"${file_name}",
        )

        return "\n".join(list(diff))
