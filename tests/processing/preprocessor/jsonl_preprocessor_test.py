import textwrap

from openhasp_config_manager.processing import JsonlPreProcessor
from tests import TestBase


class TestJsonlPreProcessor(TestBase):

    def test_empty_content(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = ""

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == ""

    def test_only_comment(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = "// test"

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == ""

    def test_comment_before_object(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = """
        // test
        { "x": 0 }
        """

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == """{ "x": 0 }"""

    def test_comment_after_object(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = """
        { "x": 0 }
        // test
        """

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == """{ "x": 0 }"""

    def test_comment_between_object(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = """
        { "x": 0 }
        // test
        { "y": 0 }
        """

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == textwrap.dedent("""
        { "x": 0 }
        { "y": 0 }
        """).strip()

    def test_inline_comment_after_object_param_with_comma_is_stripped(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = textwrap.dedent("""
        { 
            "x": 0, // comment
            "y": 0
        }
        """)

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == textwrap.dedent("""
               {
               "x": 0,
               "y": 0
               }
               """).strip()

    def test_inline_comment_after_object_param_without_comma_is_stripped(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = textwrap.dedent("""
        { 
            "x": 0, 
            "y": 0 // comment
        }
        """)

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == textwrap.dedent("""
               {
               "x": 0,
               "y": 0
               }
               """).strip()

    def test_trailing_comma_on_last_object_is_stripped(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = textwrap.dedent("""
        { 
            "x": 0,
        }
        """)

        # WHEN
        result = underTest.cleanup_object_for_json_parsing(content)

        # THEN
        assert result == textwrap.dedent("""
               {
               "x": 0
               }
               """).strip()

    def test_split_objects_empty_content(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = ""

        # WHEN
        result = underTest.split_jsonl_objects(content)

        # THEN
        assert result == []

    def test_split_objects_single_object_with_random_stuff_around_it(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = textwrap.dedent("""
        1237!()
        // comment
        random text
        { "x": 0 }
        random stuff
        // comment
        1237!()
        """).strip()

        # WHEN
        result = underTest.split_jsonl_objects(content)

        # THEN
        assert result == ["""{ "x": 0 }"""]

    def test_split_objects_multiple_objects_with_random_stuff_around_them(self):
        # GIVEN
        underTest = JsonlPreProcessor()

        content = textwrap.dedent("""
        1237!()
        // comment
        random text
        { "x": 0 }
        random stuff
        // comment
        1237!()
        { "y": 1 }
        random stuff
        // comment
        1237!()

        """).strip()

        # WHEN
        result = underTest.split_jsonl_objects(content)

        # THEN
        assert result == [
            """{ "x": 0 }""",
            """{ "y": 1 }""",
        ]
