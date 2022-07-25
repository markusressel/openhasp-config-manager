import textwrap

from openhasp_config_manager.processor import Processor
from tests import TestBase


class ProcessorTest(TestBase):

    def test_multiline_object_params(self):
        processor = Processor()

        content = textwrap.dedent("""
           { 
             "x": 0,
             "y": 0 
           }
           """)

        result = processor.process_jsonl(content)

        self.assertEquals(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()
        )

    def test_ignore_line_comment_between_object_params(self):
        processor = Processor()

        content = textwrap.dedent("""
           { 
             "x": 0,
             // this is a comment 
             "y": 0 
           }
           """)

        result = processor.process_jsonl(content)

        self.assertEquals(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               """).strip()
        )

    def test_ignore_line_comment_between_objects(self):
        processor = Processor()

        content = textwrap.dedent("""
           { "x": 0, "y": 0 }
           // this is a comment
           { "a": 0, "b": 0 }
           """)

        result = processor.process_jsonl(content)

        self.assertEquals(
            result,
            textwrap.dedent("""
               {"x": 0, "y": 0}
               {"a": 0, "b": 0}
               """).strip()
        )

    def test_multiple_objects(self):
        processor = Processor()

        content = textwrap.dedent("""
        { "x": 0, "y": 0 }
        { "a": 0, "b": 0 }
        """)

        result = processor.process_jsonl(content)

        self.assertEquals(
            result,
            textwrap.dedent("""
            {"x": 0, "y": 0}
            {"a": 0, "b": 0}
            """).strip()
        )
