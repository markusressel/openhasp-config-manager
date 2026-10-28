from dataclasses import replace
from typing import Dict, List, Set


from openhasp_config_manager.deployment import _delete_after_restart
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.webservice_client import FileInUseError
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.uploader import ConfigUploader
from tests import TestBase


class FakeClient:
    """The parts of OpenHaspClient the uploader uses, async like the real ones, against an in-memory plate."""

    def __init__(self, device):
        self.files: Dict[str, bytes] = {}
        self.uploaded: List[str] = []
        self.deleted: List[str] = []
        self.mqtt_config = device.config.mqtt
        self.http_config = device.config.http
        self.gui_config = device.config.gui
        # like the plate, which doesn't tell its passwords
        self.mask_passwords = False
        self.applied_live: List[dict] = []
        # like the plate, which can't delete the TrueType fonts it uses
        self.in_use: Set[str] = set()
        self.restarted = False

    async def get_files(self) -> List[str]:
        return list(self.files)

    async def get_file_content(self, file_name: str) -> bytes:
        return self.files[file_name]

    async def upload_file(self, name: str, content: bytes):
        self.files[name] = content
        self.uploaded.append(name)

    async def delete_file(self, file_name: str):
        if file_name in self.in_use:
            raise FileInUseError(file_name)
        del self.files[file_name]
        self.deleted.append(file_name)

    async def wait_for_restart(self) -> bool:
        # the new pages don't use the files the old ones did
        self.restarted = True
        self.in_use = set()
        return True

    async def get_mqtt_config(self):
        return replace(self.mqtt_config, password="********") if self.mask_passwords else self.mqtt_config

    async def set_mqtt_config(self, config):
        self.mqtt_config = config

    async def get_http_config(self):
        return replace(self.http_config, password="********") if self.mask_passwords else self.http_config

    async def set_http_config(self, config):
        self.http_config = config

    async def apply_gui_settings(self, settings):
        self.applied_live.append(settings)

    async def get_gui_config(self):
        return self.gui_config

    async def set_gui_config(self, config):
        self.gui_config = config


class TestConfigUploader(TestBase):
    def _processed_device(self, output_dir):
        manager = ConfigManager(self.cfg_root, output_dir, VariableManager(self.cfg_root))
        device = manager.analyze()[0]
        manager.process(device)
        return device

    async def test_uploads_every_generated_file(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)

        # WHEN
        changed = await ConfigUploader(tmp_path, client).upload(device)

        # THEN
        assert changed is True
        assert sorted(client.uploaded) == sorted(file.name for file in device.output_dir.iterdir())

    async def test_unchanged_files_are_not_uploaded_again(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        uploader = ConfigUploader(tmp_path, client)
        await uploader.upload(device)
        client.uploaded.clear()

        # WHEN
        changed = await uploader.upload(device)

        # THEN
        assert changed is False
        assert client.uploaded == []

    async def test_purge_deletes_files_that_are_not_generated(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.files = {"old.jsonl": b"{}", "config.json": b"{}"}

        # WHEN
        await ConfigUploader(tmp_path, client).upload(device, purge=True)

        # THEN
        assert client.deleted == ["old.jsonl"]

    async def test_purge_keeps_a_file_the_plate_uses_and_restarts_it(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.files = {"old.ttf": b"font", "old.jsonl": b"{}", "config.json": b"{}"}
        client.in_use = {"old.ttf"}

        # WHEN
        result = await ConfigUploader(tmp_path, client).upload_changes(device, purge=True)

        # THEN
        assert result.deleted == ["old.jsonl"]
        assert result.in_use == ["old.ttf"]
        assert result.needs_restart

    async def test_a_file_the_plate_used_is_deleted_after_it_restarted(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.files = {"old.ttf": b"font", "config.json": b"{}"}
        client.in_use = {"old.ttf"}

        # WHEN
        await _delete_after_restart(client, ConfigUploader(tmp_path, client), device, ["old.ttf"])

        # THEN
        assert client.restarted
        assert client.deleted == ["old.ttf"]

    async def test_upload_changes_tells_what_changed(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.files = {"old.jsonl": b"{}", "config.json": b"{}"}
        uploader = ConfigUploader(tmp_path, client)

        # WHEN
        result = await uploader.upload_changes(device, purge=True)

        # THEN
        assert sorted(result.files) == sorted(file.name for file in device.output_dir.iterdir())
        assert result.deleted == ["old.jsonl"]
        assert result.changed
        assert not (await uploader.upload_changes(device)).changed

    async def test_masked_passwords_do_not_count_as_a_change(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.mask_passwords = True
        uploader = ConfigUploader(tmp_path, client)

        # WHEN
        first = await uploader.upload_changes(device)
        second = await uploader.upload_changes(device)

        # THEN the passwords are sent once, since nothing says they are on the plate. Then the plate has them.
        assert first.config_changed
        assert not second.config_changed

    async def test_changed_password_is_sent_when_the_plate_masks_it(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.mask_passwords = True
        uploader = ConfigUploader(tmp_path, client)
        await uploader.upload_changes(device)
        device.config.mqtt = replace(device.config.mqtt, password="new")

        # WHEN
        result = await uploader.upload_changes(device)

        # THEN
        assert result.config_changed
        assert client.mqtt_config.password == "new"

    async def test_idle_timeouts_are_applied_to_the_running_plate(self, tmp_path):
        # GIVEN the plate has other idle timeouts, like haad leaves them
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.gui_config = replace(device.config.gui, idle1=15, idle2=0)

        # WHEN
        result = await ConfigUploader(tmp_path, client).upload_changes(device)

        # THEN no restart is needed
        assert result.settings_applied
        assert not result.config_changed
        assert result.changed
        assert not result.needs_restart
        assert client.applied_live == [{"idle1": device.config.gui.idle1, "idle2": device.config.gui.idle2}]

    async def test_rotation_needs_a_restart(self, tmp_path):
        # GIVEN
        device = self._processed_device(tmp_path)
        client = FakeClient(device)
        client.gui_config = replace(device.config.gui, rotate=(device.config.gui.rotate or 0) + 1)

        # WHEN
        result = await ConfigUploader(tmp_path, client).upload_changes(device)

        # THEN
        assert result.config_changed
        assert result.needs_restart
        assert client.applied_live == []
