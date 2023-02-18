from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing import VariableManager
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
        assert len(components) == 6

    def test_global_variable(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        manager = ConfigManager(self.cfg_root, tmp_path, variable_manager)
        devices = manager.analyze()

        # WHEN
        tested_component_path = Path(self.cfg_root, "test_device", "home_page.jsonl")
        result = variable_manager.get_vars(tested_component_path)

        # THEN
        assert result == {
            "global": {
                "var": "global_var_value"
            },
            "key_also_present_in_device_vars": "global_value"
        }