from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestConfigManager(TestBase):
    def test_analyze_whole_config(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        manager = ConfigManager(self.cfg_root, tmp_path, variable_manager)

        # WHEN
        devices = manager.analyze()

        # THEN
        assert len(devices) == 1

        device = devices[0]
        assert len(device.cmd) == 3
        assert len(device.jsonl) == 4
        assert len(device.images) == 1
        assert len(device.fonts) == 0
