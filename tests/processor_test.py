import textwrap

from openhasp_config_manager.model import Component
from openhasp_config_manager.processor import DeviceProcessor, JsonlObjectProcessor
from tests import TestBase


class ProcessorTest(TestBase):

    def test_multiline_object_params(self):
        config = self.default_config

        jsonl_object_processor = JsonlObjectProcessor()
        processor = DeviceProcessor(config, jsonl_object_processor)

        content = textwrap.dedent("""
           { 
             "x": 0,
             "y": 0 
           }
           """)

        component = Component(
            name="component",
            type="jsonl",
            path=None,
            content=content
        )

        result = processor.normalize(component)

        self.assertEqual(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()
        )

    def test_ignore_line_comment_between_object_params(self):
        config = self.default_config

        jsonl_object_processor = JsonlObjectProcessor()
        processor = DeviceProcessor(config, jsonl_object_processor)

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
            path=None,
            content=content
        )

        result = processor.normalize(component)

        self.assertEqual(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()
        )

    def test_ignore_line_comment_between_objects(self):
        config = self.default_config

        jsonl_object_processor = JsonlObjectProcessor()
        processor = DeviceProcessor(config, jsonl_object_processor)

        content = textwrap.dedent("""
           { "x": 0, "y": 0 }
           // this is a comment
           { "a": 0, "b": 0 }
           """)

        component = Component(
            name="component",
            type="jsonl",
            path=None,
            content=content
        )

        result = processor.normalize(component)

        self.assertEqual(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               {"a": 0, "b": 0}
               """).strip()
        )

    def test_multiple_objects(self):
        config = self.default_config

        jsonl_object_processor = JsonlObjectProcessor()
        processor = DeviceProcessor(config, jsonl_object_processor)

        content = textwrap.dedent("""
            { "x": 0, "y": 0 }
            { "a": 0, "b": 0 }
            """)

        component = Component(
            name="component",
            type="jsonl",
            path=None,
            content=content
        )

        result = processor.normalize(component)

        self.assertEqual(
            result,
            textwrap.dedent("""
            {"x": 0, "y": 0}
            {"a": 0, "b": 0}
            """).strip()
        )
