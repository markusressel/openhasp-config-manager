import pytest

from openhasp_config_manager.cli.common import _create_config_manager, _deploy
from openhasp_config_manager.deployment import obsolete_files
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.uploader import ConfigUploader, UploadResult
from tests import TestBase


class TestDeploy(TestBase):
    async def _deploy(self, tmp_path, monkeypatch, result: UploadResult, restart: bool = False):
        actions = []

        async def upload_changes(uploader, device, purge, show_diff):
            return result

        async def reboot(client):
            actions.append("reboot")

        async def restore_from_files(client):
            actions.append("reload")

        monkeypatch.setattr(ConfigUploader, "upload_changes", upload_changes)
        monkeypatch.setattr(OpenHaspClient, "reboot", reboot)
        monkeypatch.setattr(OpenHaspClient, "restore_from_files", restore_from_files)
        config_manager = _create_config_manager(self.cfg_root, tmp_path)
        device = config_manager.analyze()[0]

        await _deploy(config_manager, device, purge=False, show_diff=False, restart=restart)
        return actions

    async def test_reloads_pages_when_only_pages_changed(self, tmp_path, monkeypatch):
        result = UploadResult(files=["pages.jsonl", "boot.cmd", "icon.png"])
        assert await self._deploy(tmp_path, monkeypatch, result) == ["reload"]

    @pytest.mark.parametrize(
        "result", [UploadResult(config_changed=True), UploadResult(files=["arial20.ttf"]), UploadResult(files=["a.bin"])]
    )
    async def test_reboots_when_the_plate_loads_it_at_startup(self, tmp_path, monkeypatch, result):
        assert await self._deploy(tmp_path, monkeypatch, result) == ["reboot"]

    async def test_reboots_when_a_deleted_file_is_a_font(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, UploadResult(deleted=["old.ttf"])) == ["reboot"]

    async def test_applied_settings_need_no_reload(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, UploadResult(settings_applied=True)) == []

    async def test_restart_option_reboots_for_any_change(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, UploadResult(files=["pages.jsonl"]), restart=True) == ["reboot"]

    async def test_nothing_without_changes(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, UploadResult()) == []
        assert await self._deploy(tmp_path, monkeypatch, UploadResult(), restart=True) == []


class TestObsoleteFiles(TestBase):
    async def test_are_the_files_on_the_plate_that_are_not_in_the_generated_output(self, tmp_path, monkeypatch):
        # GIVEN
        config_manager = _create_config_manager(self.cfg_root, tmp_path)
        device = config_manager.analyze()[0]

        async def get_files(client):
            return ["config.json", "old_page.jsonl", "home_page.jsonl", "old_font.ttf"]

        monkeypatch.setattr(OpenHaspClient, "get_files", get_files)

        # WHEN
        files = await obsolete_files(config_manager, device)

        # THEN: config.json and the generated files stay
        assert files == ["old_page.jsonl", "old_font.ttf"]
