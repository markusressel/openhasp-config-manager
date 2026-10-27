from openhasp_config_manager.gui.domain.variables.references import object_type_uses, part_at, scan_text, variable_uses
from tests import TestBase


def _names(line):
    return [(line[part.start : part.end], part.name) for use in variable_uses(line) for part in use.parts]


class TestVariableUses(TestBase):
    def test_every_part_of_a_variable_stands_for_the_variable_up_to_it(self):
        assert _names('"h": "{{ common.header.bar.height }}",') == [
            ("common", "common"),
            ("header", "common.header"),
            ("bar", "common.header.bar"),
            ("height", "common.header.bar.height"),
        ]

    def test_a_use_is_the_whole_variable(self):
        line = '"h": "{{ common.header }}"'
        [use] = variable_uses(line)
        assert (use.name, line[use.start : use.end]) == ("common.header", "common.header")

    def test_filters_keywords_strings_and_functions_are_no_variables(self):
        line = '"t": "{{ \'a.b\' ~ name if flag else other | upper }}{{ range(3) }}"'
        assert _names(line) == [("name", "name"), ("flag", "flag"), ("other", "other")]

    def test_a_method_is_a_use_of_the_object_it_belongs_to(self):
        assert _names("{{ items.keys() }}") == [("items", "items")]
        assert _names("{% for k in a.b.items() %}") == [("a", "a"), ("b", "a.b")]

    def test_what_a_loop_or_set_defines_is_no_variable(self):
        assert _names("{% for k, v in a.items() %}{{ v }}") == [("a", "a"), ("v", "v")]
        assert _names("{% set x = y.z %}") == [("y", "y"), ("z", "y.z")]

    def test_subscripts_stop_the_variable_and_are_variables_themselves(self):
        assert _names("{{ a.b[page] }}") == [("a", "a"), ("b", "a.b"), ("page", "page")]

    def test_templates_in_other_text(self):
        assert _names("run L:/{{ page.name }}.jsonl") == [("page", "page"), ("name", "page.name")]
        assert _names('"x": 10, "y": "plain"') == []

    def test_statements_and_comments(self):
        assert _names("{% if theme.dark %}") == [("theme", "theme"), ("dark", "theme.dark")]
        assert _names("{# a.b #}") == []

    def test_part_at(self):
        line = '"h": "{{ common.header }}"'
        assert part_at(line, 10).name == "common"
        assert part_at(line, 18).name == "common.header"
        assert part_at(line, 15) is None
        assert part_at(line, 2) is None


class TestObjectTypeUses(TestBase):
    def test_object_types_have_the_theme_of_their_type(self):
        line = '{"obj": "btn", "text": "{{ a }}"}'
        [use] = object_type_uses(line)
        assert (use.type, use.variable, line[use.start : use.end]) == ("btn", "theme.obj.btn", "btn")

    def test_types_from_templates_are_not_known(self):
        assert object_type_uses('{"obj": "{{ t }}"}') == []


class TestScanText(TestBase):
    def test_lists_the_lines_that_use_anything(self):
        text = 'no\n{"obj": "btn", "t": "{{ a }}"}\n\n{"x": "{{ b.c }}"}\n'
        assert [
            (number, [use.name for use in uses], [use.type for use in types]) for number, uses, types in scan_text(text)
        ] == [
            (2, ["a"], ["btn"]),
            (4, ["b.c"], []),
        ]
