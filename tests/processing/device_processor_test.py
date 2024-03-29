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
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           { 
             "x": 0,
             "y": 0 
           }
           """)

        component = JsonlComponent(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "common"),
            content=content
        )

        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()

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
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
            { "x": 0, "y": 0 }
            { "a": 0, "b": 0 }
            """)

        component = JsonlComponent(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == textwrap.dedent("""
            {"x": 0, "y": 0}
            {"a": 0, "b": 0}
            """).strip()

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
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
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
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == textwrap.dedent("""
               {"id": 0, "page": 1, "x": 0, "y": 0}
               {"id": 1, "page": 1, "x": 0, "y": 0}
               {"id": 2, "page": 1, "x": 0, "y": 0}
               """).strip()

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
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           {
             "w": "{{ device.screen.width }}"
           }
           """)

        component = JsonlComponent(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == textwrap.dedent(f"""
               {{"w": {device.config.openhasp_config_manager.device.screen.width}}}
               """).strip()

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
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        variable_manager.add_vars(
            vars={
                "id": {
                    "text": 10
                }
            },
            path=device.path,
        )

        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           {
             "id": "{{ id.text }}"
           }
           """)

        component = JsonlComponent(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )
        processor._add_jsonl(component)

        # WHEN
        result = processor.normalize(device, component)

        # THEN
        assert result == textwrap.dedent(f"""
               {{"id": 10}}
               """).strip()
