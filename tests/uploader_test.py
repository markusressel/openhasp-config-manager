from typing import Dict, List

from openhasp_config_manager.manager import ConfigManager
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

    async def get_files(self) -> List[str]:
        return list(self.files)

    async def get_file_content(self, file_name: str) -> bytes:
        return self.files[file_name]

    async def upload_file(self, name: str, content: bytes):
        self.files[name] = content
        self.uploaded.append(name)

    async def delete_file(self, file_name: str):
        del self.files[file_name]
        self.deleted.append(file_name)

    async def get_mqtt_config(self):
        return self.mqtt_config

    async def set_mqtt_config(self, config):
        self.mqtt_config = config

    async def get_http_config(self):
        return self.http_config

    async def set_http_config(self, config):
        self.http_config = config

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
