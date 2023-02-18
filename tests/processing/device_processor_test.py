import textwrap
from pathlib import Path

from openhasp_config_manager.model import Component, Device
from openhasp_config_manager.processing import DeviceProcessor, VariableManager
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from tests import TestBase


class TestDeviceProcessor(TestBase):

    def test_multiline_object_params(self):
        # GIVEN
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
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

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "common"),
            content=content
        )

        # WHEN
        result = processor.normalize(component)

        # THEN
        assert result == textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()

    def test_ignore_line_comment_between_object_params(self):
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
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
             // this is a comment 
             "y": 0 
           }
           """)

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )

        result = processor.normalize(component)

        assert result == textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()

    def test_ignore_line_comment_between_objects(self):
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
            output_dir=None
        )

        variable_manager = VariableManager(self.cfg_root)
        jsonl_object_processors = [
            ObjectDimensionsProcessor()
        ]
        processor = DeviceProcessor(device, jsonl_object_processors, variable_manager)

        content = textwrap.dedent("""
           { "x": 0, "y": 0 }
           // this is a comment
           { "a": 0, "b": 0 }
           """)

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )

        result = processor.normalize(component)

        assert result == textwrap.dedent("""
               {"x": 0, "y": 0}
               {"a": 0, "b": 0}
               """).strip()

    def test_multiple_objects(self):
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
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

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )

        result = processor.normalize(component)

        assert result == textwrap.dedent("""
            {"x": 0, "y": 0}
            {"a": 0, "b": 0}
            """).strip()

    def test_id_template(self):
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
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

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )

        processor.add_jsonl(component)
        result = processor.normalize(component)

        assert result == textwrap.dedent("""
               {"id": 0, "page": 1, "x": 0, "y": 0}
               {"id": 1, "page": 1, "x": 0, "y": 0}
               {"id": 2, "page": 1, "x": 0, "y": 0}
               """).strip()

    def test_config_value_template(self):
        device = Device(
            name="test_device",
            path=Path(self.cfg_root, "devices", "test_device"),
            config=self.default_config,
            components=[],
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

        component = Component(
            name="component",
            type="jsonl",
            path=Path(self.cfg_root, "devices", "test_device"),
            content=content
        )

        result = processor.normalize(component)

        assert result == textwrap.dedent(f"""
               {{"w": {device.config.openhasp_config_manager.device.screen.width}}}
               """).strip()
