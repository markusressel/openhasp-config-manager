from openhasp_config_manager.gui.domain.source.edit import indent_for_new_line, matching_bracket, toggle_comment
from openhasp_config_manager.gui.domain.source.syntax import Language
from tests import TestBase


class TestComments(TestBase):
    def test_comment_and_uncomment(self):
        lines = ["  {", '    "a": 1,', "", "  }"]
        commented = toggle_comment(lines, Language.JSONL)
        assert commented == ["  // {", '  //   "a": 1,', "", "  // }"]
        assert toggle_comment(commented, Language.JSONL) == lines

    def test_partly_commented_lines_get_commented(self):
        assert toggle_comment(["// a", "b"], Language.JSONL) == ["// // a", "// b"]

    def test_yaml_and_no_comments(self):
        assert toggle_comment(["a: 1"], Language.YAML) == ["# a: 1"]
        assert toggle_comment(["# a: 1"], Language.YAML) == ["a: 1"]
        assert toggle_comment(["//x"], Language.JSONL) == ["x"]
        assert toggle_comment(["run x"], Language.CMD) == ["run x"]
        assert toggle_comment(["", "  "], Language.JSONL) == ["", "  "]


class TestIndent:
    def test_keeps_the_indentation_and_indents_after_brackets(self):
        assert indent_for_new_line("  foo", Language.JSONL) == "  "
        assert indent_for_new_line("  {", Language.JSONL) == "    "
        assert indent_for_new_line("  [  ", Language.JSONL) == "    "
        assert indent_for_new_line("a:", Language.YAML) == "  "
        assert indent_for_new_line("a:", Language.JSONL) == ""
        assert indent_for_new_line("", Language.JSONL) == ""


class TestBrackets:
    TEXT = '{"a": [1, {"b": "}"}], // }\n "c": 2}'

    def test_pairs(self):
        assert matching_bracket(self.TEXT, 0) == len(self.TEXT) - 1
        assert matching_bracket(self.TEXT, len(self.TEXT) - 1) == 0
        assert matching_bracket(self.TEXT, 6) == 20
        assert matching_bracket(self.TEXT, 20) == 6
        assert matching_bracket(self.TEXT, 10) == 19

    def test_no_partner_or_no_bracket(self):
        assert matching_bracket("{", 0) is None
        assert matching_bracket("}", 0) is None
        assert matching_bracket('{"a"}', 2) is None
