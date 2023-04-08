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

        components = devices[0].components
        assert len(components) == 7
