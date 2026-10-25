from openhasp_config_manager.gui.domain.source_format import format_text
from openhasp_config_manager.gui.domain.source_syntax import Language
from tests import TestBase


class TestFormat(TestBase):
    def test_indents_by_depth(self):
        text = '  {\n"a": 1,   \n      "b": {\n"c": [\n1\n]\n  },\n}\n\n// note\n{"x": 1}\n'
        assert format_text(text, Language.JSONL) == (
            '{\n  "a": 1,\n  "b": {\n    "c": [\n      1\n    ]\n  },\n}\n\n// note\n{"x": 1}\n'
        )

    def test_brackets_in_strings_and_comments_do_not_count(self):
        assert format_text('{\n"a": "{",\n// }\n"b": 1\n}', Language.JSONL) == '{\n  "a": "{",\n  // }\n  "b": 1\n}\n'

    def test_unbalanced_closing_stays_at_the_left(self):
        assert format_text('}\n  "a"\n', Language.JSONL) == '}\n"a"\n'

    def test_line_ends_and_final_newline(self):
        assert format_text("a  \n\n\n", Language.CMD) == "a\n"
        assert format_text("a: 1  \n  b: 2\t", Language.YAML) == "a: 1\n  b: 2\n"
        assert format_text("", Language.JSONL) == ""
        assert format_text("\n\n", Language.CMD) == ""

    def test_is_stable(self):
        text = '{\n  "a": {\n    "b": 1\n  }\n}\n'
        assert format_text(text, Language.JSONL) == text
