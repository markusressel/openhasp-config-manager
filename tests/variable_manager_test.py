from pathlib import Path

from openhasp_config_manager.processing import VariableManager
from tests import TestBase


class TestVariableManager(TestBase):

    def test_global_variable(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "test_device", "home_page.jsonl")

        # WHEN
        result = variable_manager.get_vars(tested_component_path)

        # THEN
        assert result == {
            "global": {
                "var": "global_var_value"
            },
            "key_also_present_in_device_vars": "global_value"
        }
