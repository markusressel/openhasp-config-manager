from jinja2 import TemplateSyntaxError

from openhasp_config_manager.gui.domain.source_syntax import Language
from openhasp_config_manager.gui.domain.template_values import describe_value, line_colors, line_values, variable_help
from tests import TestBase

VARIABLES = {"header": {"height": 44, "title": "Living room"}, "flag": True, "items": [1, 2, 3]}


def _value(name):
    value = VARIABLES
    for part in name.split("."):
        value = value[part]
    return value


def _render(text):
    if "{{ x" in text:
        raise TemplateSyntaxError("unexpected end", 1)
    return text.replace("{{ header.height + 10 }}", "54").replace("{{ header.height }}", "44")


class TestDescribeValue(TestBase):
    def test_scalars_mappings_and_lists(self):
        assert describe_value(44) == "44"
        assert describe_value(True) == "true"
        assert describe_value(None) == "none"
        assert describe_value({"a": 1, "b": 2}) == "{a, b}"
        assert describe_value([1, "x"]) == "[1, x]"
        assert describe_value(list(range(20))).endswith(", …]")
        assert describe_value({str(i): i for i in range(20)}).endswith(", …}")

    def test_long_values_are_cut(self):
        assert describe_value("x" * 500) == "x" * 199 + "…"


class TestVariableHelp(TestBase):
    LINE = '"h": "{{ header.height }}", "y": "{{ header.height + 10 }}"'

    def test_a_variable_shows_its_value(self):
        column = self.LINE.index("height")
        found = variable_help(self.LINE, column, _value, _render)
        assert (found.name, found.kind, found.summary) == ("header.height", "variable", "`44`")
        # the template is just the variable: no second value
        assert found.details == []

    def test_a_part_of_a_variable_shows_what_it_stands_for(self):
        found = variable_help(self.LINE, self.LINE.index("header"), _value, _render)
        assert (found.name, found.summary) == ("header", "`{height, title}`")

    def test_an_expression_also_shows_what_it_renders_to(self):
        column = self.LINE.rindex("height")
        found = variable_help(self.LINE, column, _value, _render)
        assert found.name == "header.height"
        assert found.details == [("Renders to", "`54`")]

    def test_the_operators_of_a_template_show_what_it_renders_to(self):
        column = self.LINE.index("+ 10")
        found = variable_help(self.LINE, column, _value, _render)
        assert (found.kind, found.details) == ("template", [("Renders to", "`54`")])

    def test_unknown_variables_show_only_the_rendered_template(self):
        line = '"t": "{{ nope }}"'
        found = variable_help(line, line.index("nope"), _value, lambda text: "{{ nope }}")
        assert (found.kind, found.name) == ("template", "{{ nope }}")

    def test_a_template_that_can_not_be_rendered_says_why(self):
        line = '"t": "{{ x }}"'
        found = variable_help(line, line.index("x"), _value, _render)
        assert dict(found.details)["Can't render"] == "unexpected end"

    def test_without_a_draft_only_the_variable_is_shown(self):
        found = variable_help(self.LINE, self.LINE.index("height"), _value, lambda text: None)
        assert found.summary == "`44`" and found.details == []

    def test_outside_of_templates_and_in_comments_there_is_nothing(self):
        assert variable_help(self.LINE, 2, _value, _render) is None
        assert variable_help("{# header.height #}", 6, _value, _render) is None

    def test_backticks_of_values_do_not_end_the_code(self):
        found = variable_help('"t": "{{ flag }}"', 11, lambda name: "a`b", _render)
        assert found.summary == "`a'b`"


class TestLineValues(TestBase):
    def test_every_template_of_the_line_in_order(self):
        assert line_values('"h": "{{ header.height }}", "y": "{{ header.height + 10 }}"', _render) == ["44", "54"]

    def test_statements_broken_templates_and_lines_without_are_left_out(self):
        assert line_values("{% if flag %}", _render) == []
        assert line_values('"t": "{{ x }}"', _render) == []
        assert line_values("no template", _render) == []
        assert line_values('"t": "{{ header.height }}"', lambda text: None) == []


class TestLineColors(TestBase):
    def test_color_strings_and_templates_that_render_to_a_color(self):
        def render(text):
            return "#00FF00" if "green" in text else "12"

        line = '{"bg_color": "#FF0000", "text_color": "{{ green }}", "w": "{{ w }}"}'

        colors = line_colors(line, Language.JSONL, render)

        assert [color.hex() for color in colors] == ["#FF0000", "#00FF00"]

    def test_without_draft_only_color_strings(self):
        colors = line_colors('{"bg_color": "#abc", "x": "{{ y }}"}', Language.JSONL, None)

        assert len(colors) == 1

    def test_unrenderable_template_is_left_out(self):
        def render(text):
            raise TemplateSyntaxError("bad", 1)

        assert line_colors('{"bg_color": "{{ y }}"}', Language.JSONL, render) == []
