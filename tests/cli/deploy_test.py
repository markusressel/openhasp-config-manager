from openhasp_config_manager.cli import common
from openhasp_config_manager.cli.common import _create_config_manager, _deploy
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests import TestBase


class TestDeploy(TestBase):
    async def _deploy(self, tmp_path, monkeypatch, changed: bool):
        reboots = []

        async def upload(device, output_dir, purge, show_diff):
            return changed

        async def reboot(client):
            reboots.append(client._device.name)

        monkeypatch.setattr(common, "_upload", upload)
        monkeypatch.setattr(OpenHaspClient, "reboot", reboot)
        config_manager = _create_config_manager(self.cfg_root, tmp_path)
        device = config_manager.analyze()[0]

        await _deploy(config_manager, device, tmp_path, purge=False, show_diff=False)
        return reboots

    async def test_reboots_when_files_changed(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, changed=True) == ["test_device"]

    async def test_no_reboot_without_changes(self, tmp_path, monkeypatch):
        assert await self._deploy(tmp_path, monkeypatch, changed=False) == []
