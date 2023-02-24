from pathlib import Path

from openhasp_config_manager.processing import VariableManager
from tests import TestBase


class TestVariableManager(TestBase):

    # def test_vars_function(self, tmp_path):
    # TODO: implement this?
    #     # GIVEN
    #     variable_manager = VariableManager(self.cfg_root)
    #
    #     input_data = {
    #         "A": "{{ vars('global.var') }}",
    #     }
    #
    #     template_vars = {}
    #
    #     # WHEN
    #     result = render_dict_recursive(
    #         input=input_data,
    #         template_vars=template_vars
    #     )
    #
    #     # THEN
    #     assert result == {
    #         'A': 'global_var_value',
    #     }

    def test_global_variable(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        result = variable_manager.get_vars(tested_component_path)

        # THEN
        assert result == {
            "global": {
                "var": "global_var_value"
            },
            'key_vars2': 'value_vars2',
            "key_also_present_in_device_vars": "test_device_value"
        }

    def test_add_var(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        variable_manager.add_var(
            key="A",
            value="B",
            path=tested_component_path,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": "B",
            "global": {
                "var": "global_var_value"
            },
            'key_vars2': 'value_vars2',
            "key_also_present_in_device_vars": "test_device_value"
        }

    def test_add_var_global(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        variable_manager.add_var(
            key="A",
            value="B",
            path=self.cfg_root,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": "B",
            "global": {
                "var": "global_var_value"
            },
            'key_vars2': 'value_vars2',
            "key_also_present_in_device_vars": "test_device_value"
        }

    def test_add_vars(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        variable_manager.add_vars(
            vars={
                "A": {
                    "B": "C"
                }
            },
            path=tested_component_path,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": {
                "B": "C"
            },
            "global": {
                "var": "global_var_value"
            },
            'key_vars2': 'value_vars2',
            "key_also_present_in_device_vars": "test_device_value"
        }

    def test_add_vars_merge_with_existing(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        variable_manager.add_vars(
            vars={
                "A": {
                    "B": "C"
                }
            },
            path=tested_component_path,
        )

        # WHEN
        variable_manager.add_vars(
            vars={
                "A": {
                    "B": "D",
                    "C": "E"
                }
            },
            path=tested_component_path,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": {
                "B": "D",
                "C": "E"
            },
            "global": {
                "var": "global_var_value"
            },
            'key_vars2': 'value_vars2',
            "key_also_present_in_device_vars": "test_device_value"
        }
