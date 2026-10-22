import dataclasses

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestRestoreFromFiles(TestBase):
    def _client(self, tmp_path, monkeypatch, files, **hasp):
        device = ConfigManager(self.cfg_root, tmp_path, VariableManager(self.cfg_root)).analyze()[0]
        device.config.hasp = dataclasses.replace(device.config.hasp, **hasp)
        client = OpenHaspClient(device)
        commands = []

        async def get_files():
            return files

        async def command(keyword=None, params=None):
            commands.append((keyword, params))

        monkeypatch.setattr(client, "get_files", get_files)
        monkeypatch.setattr(client, "command", command)
        return client, commands

    async def test_runs_the_startup_files_like_a_restart(self, tmp_path, monkeypatch):
        # GIVEN
        client, commands = self._client(
            tmp_path, monkeypatch, ["pages.jsonl", "boot.cmd", "online.cmd"], pages="/pages.jsonl", startpage=2
        )

        # WHEN
        await client.restore_from_files()

        # THEN
        assert commands == [
            ("clearpage", "all"),
            ("run", "/pages.jsonl"),
            ("page", "2"),
            ("run", "/boot.cmd"),
            ("run", "/online.cmd"),
        ]

    async def test_files_that_are_not_on_the_plate_are_skipped(self, tmp_path, monkeypatch):
        # GIVEN
        client, commands = self._client(tmp_path, monkeypatch, ["boot.cmd"], pages="/pages.jsonl", startpage=1)

        # WHEN
        await client.restore_from_files()

        # THEN
        assert commands == [("clearpage", "all"), ("page", "1"), ("run", "/boot.cmd")]
