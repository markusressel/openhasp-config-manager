from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestSetAnsiColors(TestBase):
    async def test_sends_the_debug_config_command(self, tmp_path, monkeypatch):
        # GIVEN
        device = ConfigManager(self.cfg_root, tmp_path, VariableManager(self.cfg_root)).analyze()[0]
        client = OpenHaspClient(device)
        commands = []

        async def command(keyword=None, params=None):
            commands.append((keyword, params))

        monkeypatch.setattr(client, "command", command)

        # WHEN
        await client.set_ansi_colors(True)
        await client.set_ansi_colors(False)

        # THEN
        assert commands == [("config/debug", '{"ansi":1}'), ("config/debug", '{"ansi":0}')]
