from pathlib import Path

import pytest

from openhasp_config_manager.processing.template_rendering import TemplateRenderError
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestVariableManager(TestBase):
    def test_global_variable(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        variable_manager.read()
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        result = variable_manager.get_vars(tested_component_path)

        # THEN
        assert result == {
            "global": {"var": "global_var_value"},
            "key_vars2": "value_vars2",
            "key_also_present_in_device_vars": "test_device_value",
        }

    def test_a_resolved_path_while_the_config_directory_is_relative(self, tmp_path, monkeypatch):
        # GIVEN: the config directory given relative to the working directory (`gui -c ./configs`)
        monkeypatch.chdir(self.cfg_root.parent)
        variable_manager = VariableManager(Path(".", self.cfg_root.name))
        variable_manager.read()
        page = Path(self.cfg_root.name, "devices", "test_device", "home", "page.jsonl")

        # WHEN: e.g. the path of a file the editor shows
        result = variable_manager.get_vars(page.resolve())

        # THEN
        assert result == variable_manager.get_vars(page)
        assert result["global"] == {"var": "global_var_value"}

        # WHEN
        variable_manager.add_var(key="A", value="B", path=page.resolve())

        # THEN
        assert variable_manager.get_vars(page)["A"] == "B"

    def test_add_var(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        variable_manager.read()
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
            "global": {"var": "global_var_value"},
            "key_vars2": "value_vars2",
            "key_also_present_in_device_vars": "test_device_value",
        }

    def test_add_var_global(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        variable_manager.read()
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
            "global": {"var": "global_var_value"},
            "key_vars2": "value_vars2",
            "key_also_present_in_device_vars": "test_device_value",
        }

    def test_add_vars(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        variable_manager.read()
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        # WHEN
        variable_manager.add_vars(
            vars={"A": {"B": "C"}},
            path=tested_component_path,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": {"B": "C"},
            "global": {"var": "global_var_value"},
            "key_vars2": "value_vars2",
            "key_also_present_in_device_vars": "test_device_value",
        }

    def test_add_vars_merge_with_existing(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        variable_manager.read()
        tested_component_path = Path(self.cfg_root, "devices", "test_device", "home", "page.jsonl")

        variable_manager.add_vars(
            vars={"A": {"B": "C"}},
            path=tested_component_path,
        )

        # WHEN
        variable_manager.add_vars(
            vars={"A": {"B": "D", "C": "E"}},
            path=tested_component_path,
        )

        # THEN
        result = variable_manager.get_vars(tested_component_path)
        assert result == {
            "A": {"B": "D", "C": "E"},
            "global": {"var": "global_var_value"},
            "key_vars2": "value_vars2",
            "key_also_present_in_device_vars": "test_device_value",
        }

    def test_variables_may_be_named_like_the_methods_of_a_dict(self, tmp_path):
        # GIVEN
        (tmp_path / "vars.yaml").write_text("menu:\n  items: [a, b]\n  values: 3\n")
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()

        # WHEN
        result = variable_manager.get_vars(tmp_path)

        # THEN
        from openhasp_config_manager.processing.template_rendering import render_template

        assert result == {"menu": {"items": ["a", "b"], "values": 3}}
        assert render_template("{{ menu.items[1] }}{{ menu.values }}", result) == "b3"

    def test_templates_are_computed_with_the_variables_of_the_path(self, tmp_path):
        # GIVEN: a computed value, and a device that overrides what it is computed from
        (tmp_path / "global.vars.yaml").write_text('margin: 4\ncard:\n  x: "{{ margin }}"\n  w: "{{ 100 - card.x * 2 }}"\n')
        device_path = tmp_path / "devices" / "plate"
        device_path.mkdir(parents=True)
        (device_path / "vars.yaml").write_text("margin: 10\n")
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()

        # THEN
        assert variable_manager.get_vars(tmp_path)["card"] == {"x": 4, "w": 92}
        assert variable_manager.get_vars(device_path)["card"] == {"x": 10, "w": 80}
        assert variable_manager.get_raw_vars(device_path)["card"]["x"] == "{{ margin }}"

    def test_the_context_can_be_used_but_is_not_part_of_the_result(self, tmp_path):
        # GIVEN
        (tmp_path / "vars.yaml").write_text('half: "{{ device.width / 2 }}"\n')
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()

        # THEN
        assert variable_manager.get_vars(tmp_path, {"device": {"width": 320}}) == {"half": 160}

    def test_a_template_that_cannot_be_computed_is_an_error(self, tmp_path):
        # GIVEN
        (tmp_path / "vars.yaml").write_text('a: "{{ b }}"\nb: "{{ a }}"\n')
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()

        # THEN
        with pytest.raises(TemplateRenderError, match="cycle: a -> b -> a"):
            variable_manager.get_vars(tmp_path)
