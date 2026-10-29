import textwrap
from pathlib import Path

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.device_processor import DeviceProcessor
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestDeviceProcessor(TestBase):
    def test_multiline_object_params(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [ObjectDimensionsProcessor()]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           { 
             "x": 0,
             "y": 0 
           }
           """)

        component = JsonlComponent(name="component", type="jsonl", path=Path(self.cfg_root, "common"), content=content)

        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert (
            result
            == textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()
        )

    def test_multiple_objects(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [ObjectDimensionsProcessor()]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
            { "x": 0, "y": 0 }
            { "a": 0, "b": 0 }
            """)

        component = JsonlComponent(
            name="component", type="jsonl", path=Path(self.cfg_root, "devices", "test_device"), content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert (
            result
            == textwrap.dedent("""
            {"x": 0, "y": 0}
            {"a": 0, "b": 0}
            """).strip()
        )

    def test_id_template(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [ObjectDimensionsProcessor()]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           {
             "id": "{{ p1b1.id - 1 }}",
             "page": "{{ p1b1.page }}",
             "x": 0,
             "y": 0 
           }
           { 
             "id": 1,
             "page": 1,
             "x": 0,
             "y": 0 
           }
           {
             "id": "{{ p1b1.id + 1 }}",
             "page": "{{ p1b1.page }}",
             "x": 0,
             "y": 0 
           }
           """)

        component = JsonlComponent(
            name="component", type="jsonl", path=Path(self.cfg_root, "devices", "test_device"), content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert (
            result
            == textwrap.dedent("""
               {"id": 0, "page": 1, "x": 0, "y": 0}
               {"id": 1, "page": 1, "x": 0, "y": 0}
               {"id": 2, "page": 1, "x": 0, "y": 0}
               """).strip()
        )

    def test_config_value_template(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [ObjectDimensionsProcessor()]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           {
             "w": "{{ device.screen.width }}"
           }
           """)

        component = JsonlComponent(
            name="component", type="jsonl", path=Path(self.cfg_root, "devices", "test_device"), content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert (
            result
            == textwrap.dedent(f"""
               {{"w": {device.config.openhasp_config_manager.device.screen.width}}}
               """).strip()
        )

    def test_id_from_config_through_template(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )

        variable_manager = VariableManager(self.cfg_root)
        variable_manager.add_vars(
            vars={"id": {"text": 10}},
            path=device.path,
        )

        jsonl_object_processors = [ObjectDimensionsProcessor()]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           {
             "id": "{{ id.text }}"
           }
           """)

        component = JsonlComponent(
            name="component", type="jsonl", path=Path(self.cfg_root, "devices", "test_device"), content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert (
            result
            == textwrap.dedent("""
               {"id": 10}
               """).strip()
        )


class TestComputedVariables(TestBase):
    def test_a_device_override_changes_the_values_computed_from_it_in_common_files(self, tmp_path):
        # GIVEN: a value computed from `margin` and the screen, used by a file of the common folder
        (tmp_path / "global.vars.yaml").write_text(
            'margin: 4\ncard:\n  x: "{{ margin }}"\n  w: "{{ device.screen.width - card.x * 2 }}"\n'
        )
        (tmp_path / "common").mkdir()
        device_path = tmp_path / "devices" / "plate"
        device_path.mkdir(parents=True)
        (device_path / "vars.yaml").write_text("margin: 10\n")
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()
        device = Device(
            name="plate", path=device_path, config=self.default_config, cmd=[], jsonl=[], images=[], fonts=[], output_dir=None
        )
        processor = DeviceProcessor(device, [ObjectDimensionsProcessor()], variable_manager)
        component = JsonlComponent(
            name="common_page.jsonl",
            type="jsonl",
            path=tmp_path / "common" / "page.jsonl",
            content='{"page": 1, "id": 1, "x": "{{ card.x }}", "w": "{{ card.w }}"}',
        )
        processor.add_component(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == '{"page": 1, "id": 1, "x": 10, "w": 300}'
        assert processor.path_variables(component.path)["card"] == {"x": 10, "w": 300}
        assert processor.path_variables(tmp_path)["card"] == {"x": 4, "w": 312}


class TestObjectReferences(TestBase):
    def _render(self, content: str) -> str:
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )
        processor = DeviceProcessor(device, [ObjectDimensionsProcessor()], VariableManager(self.cfg_root))
        component = JsonlComponent(
            name="page.jsonl", type="jsonl", path=Path(self.cfg_root, "devices", "test_device", "page.jsonl"), content=content
        )
        processor.add_component(component)
        return processor.normalize(device, component)

    def test_numeric_properties_of_other_objects_are_numbers(self):
        # GIVEN: the screen of the default config is 320 wide
        content = textwrap.dedent("""
            {"page": 1, "id": 1, "x": "{{ 2 * 5 }}", "w": "50%", "h": "8", "text": "12"}
            {"page": 1, "id": 2, "x": "{{ p1b1.x + p1b1.w }}", "w": "{{ p1b1.w - 12 }}", "h": "{{ (p1b1.h | int) * 2 }}"}
            {"page": 1, "id": 3, "text": "{{ p1b1.text ~ '!' }}", "y": "{{ p1b2.x + p1b4.y }}"}
            {"page": 1, "id": 4, "y": "{{ p1b1.h }}"}
            """)

        # WHEN
        result = self._render(content).splitlines()

        # THEN
        assert result[1] == '{"page": 1, "id": 2, "x": 170, "w": 148, "h": 16}'
        assert result[2] == '{"page": 1, "id": 3, "text": "12!", "y": 178}'
