
import pytest
from jinja2 import TemplateRuntimeError, TemplateSyntaxError

from openhasp_config_manager.processing import template_rendering
from openhasp_config_manager.processing.template_rendering import (
    TemplateRenderError,
    check_template,
    referenced_variables,
    render_template,
    render_template_collecting_unknown,
    has_nested_templates,
    referenced_objects,
    template_spans,
    template_syntax_error,
)
from tests import TestBase


class TestCollectUnknown(TestBase):
    def test_no_unknown_variables(self):
        # THEN
        assert render_template_collecting_unknown("{{ a }}", {"a": 1}) == ("1", set())
        assert render_template_collecting_unknown("plain", {}) == ("plain", set())

    def test_unknown_variables(self):
        # THEN
        assert render_template_collecting_unknown("{{ a }} {{ b }} {{ c.d }}", {"a": 1, "c": {}}) == (
            "1 {{ b }} {{ d }}",
            {"b", "d"},
        )

    def test_unknown_variables_in_inner_templates(self):
        # THEN
        text, unknown = render_template_collecting_unknown("{{ p{{ n }}b1.x }}", {"n": 1, "p1b1": {}})
        assert (text, unknown) == ("{{ x }}", {"x"})

    def test_unknown_variables_that_make_a_template_invalid(self):
        # THEN
        with pytest.raises(TemplateSyntaxError):
            render_template_collecting_unknown("{{ {{ a }} }}", {})

    def test_variables_that_are_handled_are_not_unknown(self):
        # THEN
        assert render_template_collecting_unknown("{{ a | default('d') }}", {}) == ("d", set())
        assert render_template_collecting_unknown("{% if a is defined %}x{% endif %}{{ 'b' if a }}", {}) == ("", set())

    def test_the_braces_of_a_value_are_not_unknown_variables(self):
        # THEN
        assert render_template_collecting_unknown("{{ '{{ x }}' }}", {}) == ("{{ x }}", set())

    def test_collecting_does_not_leak_into_other_renders(self):
        # WHEN
        render_template_collecting_unknown("{{ a }}", {})

        # THEN
        assert render_template("{{ a }}", {}) == "{{ a }}"
        assert template_rendering._UNKNOWN.get() is None

    def test_nothing_is_left_collecting_after_an_error(self):
        # WHEN
        with pytest.raises(TemplateSyntaxError):
            render_template_collecting_unknown("{{ unclosed", {})

        # THEN
        assert template_rendering._UNKNOWN.get() is None


class TestCheckTemplate(TestBase):
    def test_a_template_that_renders(self):
        # THEN
        assert check_template("{{ a }}", {"a": 1}) is None
        assert check_template("plain", {}) is None
        assert check_template("{{ p{{ page }}b1.x }}", {"page": 1, "p1b1": {"x": 1}}) is None
        assert check_template("x {{ p{{ page }}b1.x }} {{ page }}", {"page": 1, "p1b1": {"x": 1}}) is None

    def test_unknown_variables(self):
        # THEN
        assert check_template("{{ nope }}", {}).startswith("Unknown variable: ")
        assert "'nope' is undefined" in check_template("{{ nope }}", {})
        assert check_template("{{ obj.nope }}", {"obj": {}}).startswith("Unknown variable: ")
        assert check_template("{{ p{{ nope }}b1.x }}", {}).startswith("Unknown variable: ")

    def test_invalid_templates(self):
        # THEN
        assert check_template("{{ unclosed", {}).startswith("Invalid template: ")
        assert check_template("{{ 5 | no_such_filter }}", {}).startswith("Invalid template: ")

    def test_other_template_errors(self, monkeypatch):
        # GIVEN
        def fail(*_args, **_kwargs):
            raise TemplateRuntimeError("it broke")

        monkeypatch.setattr(template_rendering, "render_template", fail)

        # THEN
        assert check_template("{{ a }}", {}) == "Can't render: it broke"


class TestTemplateSyntaxError(TestBase):
    def test_valid_templates(self):
        # THEN
        assert template_syntax_error("plain") is None
        assert template_syntax_error("{{ nope }}") is None
        assert template_syntax_error("{{ p{{ page }}b1.x }}") is None
        assert template_syntax_error("{{ {{ a }} + {{ b }} }}") is None
        assert template_syntax_error("{% if a %}x{% endif %}") is None

    def test_invalid_templates(self):
        # THEN
        assert template_syntax_error("{{ unclosed").startswith("Invalid template: ")
        assert template_syntax_error("{{ 5 | no_such_filter }}").startswith("Invalid template: ")
        assert template_syntax_error("{% if a %}").startswith("Invalid template: ")

    def test_nested_templates_are_checked_on_their_own(self):
        # THEN
        assert template_syntax_error("{{ p{{ page + }}b1.x }}").startswith("Invalid template: ")
        assert template_syntax_error("{{ p{{ page }}b1.x + }}").startswith("Invalid template: ")


class TestTemplateSpans(TestBase):
    def test_nested_templates_are_one(self):
        # THEN
        assert template_spans("{{ p{{ page }}b1.x }}") == [(0, 21)]

    def test_statement_and_comment_templates(self):
        # GIVEN
        text = "a {% if x %}b{% endif %} {# c #}"

        # THEN
        assert [text[start:end] for start, end in template_spans(text)] == ["{% if x %}", "{% endif %}", "{# c #}"]

    def test_unclosed_templates_reach_the_end(self):
        # THEN
        assert template_spans("a {{ b") == [(2, 6)]
        assert template_spans("a {% b") == [(2, 6)]
        assert template_spans("a {# b") == [(2, 6)]
        assert template_spans("a {{ {{ b }}") == [(2, 12)]

    def test_text_without_templates(self):
        # THEN
        assert template_spans("a } b {") == []


class TestReferencedObjects(TestBase):
    def test_names_written_in_templates(self):
        assert referenced_objects("{{ p1b2.x + p3b4.w }} and p5b6", {}) == {"p1b2", "p3b4", "p5b6"}

    def test_text_without_templates_refers_to_nothing(self):
        assert referenced_objects("p1b2", {}) == set()

    def test_names_built_by_nested_templates(self):
        assert has_nested_templates("{{ p{{ page }}b2.x }}") and not has_nested_templates("{{ p1b2.x }}")
        assert referenced_objects("{{ p{{ page }}b2.x }}", {"page": 3}) == {"p3b2"}

    def test_none_if_a_nested_template_is_not_valid(self):
        assert referenced_objects("{{ p{{ 1 + }}b2.x }}", {}) is None


class TestReferencedVariables(TestBase):
    def test_the_names_with_their_attributes_and_keys(self):
        # THEN
        assert referenced_variables("{{ common.margin * 2 + a['b'].c + l[0] }}") == [
            ("common", "margin"),
            ("a", "b", "c"),
            ("l", 0),
        ]

    def test_names_with_keys_that_are_not_constant(self):
        # THEN
        assert referenced_variables("{{ a[i].x }}") == [("a",), ("i",)]
        assert referenced_variables("{{ (a | first).x }}") == [("a",)]

    def test_local_names_and_functions(self):
        # THEN
        assert referenced_variables("{% for i in items %}{{ i.x }}{% endfor %}{% set y = 1 %}{{ y }}") == [("items",)]
        assert referenced_variables("{{ range(n) }}") == [("n",)]
        assert referenced_variables("{{ a.keys() | list }} {{ b.c.get('x', d) }}") == [("a",), ("b", "c"), ("d",)]

    def test_templates_inside_of_templates(self):
        # THEN: the outer name is built, the inner ones are known
        assert referenced_variables("{{ p{{ page }}b1.x + a }}") == [("page",), ("a",)]

    def test_text_without_templates(self):
        assert referenced_variables("plain") == []

    def test_invalid_templates(self):
        with pytest.raises(TemplateRenderError, match="Invalid template"):
            referenced_variables("{{ 1 + }}")
