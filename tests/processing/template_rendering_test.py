import pytest
from jinja2 import TemplateRuntimeError, TemplateSyntaxError, UndefinedError

from openhasp_config_manager.processing import template_rendering
from openhasp_config_manager.processing.template_rendering import (
    check_template,
    has_unresolved_variables,
    referenced_variables,
    render_dict_recursive,
    render_template,
)
from tests import TestBase


class TestRenderTemplate(TestBase):
    def test_text_without_templates_is_unchanged(self):
        for text in ["", "x", "plain text", "run L:/page.jsonl", "100%"]:
            assert render_template(text, {}) == text

    def test_variables_and_expressions(self):
        # GIVEN
        template_vars = {"a": 2, "obj": {"x": 10, "name": "n"}}

        # THEN
        assert render_template("{{ a }}", template_vars) == "2"
        assert render_template("{{ obj.x + a }}", template_vars) == "12"
        assert render_template("x={{ obj.x }}, name={{ obj.name }}!", template_vars) == "x=10, name=n!"
        assert render_template("{% if a > 1 %}big{% else %}small{% endif %}", template_vars) == "big"
        assert render_template("{{ obj.x | int }}", template_vars) == "10"

    def test_unknown_variables_stay_as_they_are_written(self):
        # THEN
        assert render_template("{{ nope }}", {}) == "{{ nope }}"
        assert render_template("a {{ nope }} b {{ known }}", {"known": 1}) == "a {{ nope }} b 1"

    def test_an_unknown_key_of_a_dict_renders_as_a_hint(self):
        # the hint is not valid template syntax, so it counts as unresolved
        # WHEN
        result = render_template("{{ obj.nope }}", {"obj": {}})

        # THEN
        assert result == "{{ no such element: dict object['nope'] }}"
        assert has_unresolved_variables(result) is True

    def test_a_property_of_an_unknown_variable_raises(self):
        # THEN
        with pytest.raises(UndefinedError):
            render_template("{{ nope.x }}", {})

    def test_strict_raises_for_unknown_variables(self):
        # THEN
        assert render_template("{{ a }}", {"a": 1}, strict=True) == "1"
        with pytest.raises(UndefinedError):
            render_template("{{ nope }}", {}, strict=True)

    def test_an_invalid_template_raises(self):
        # THEN
        for text in ["{{ unclosed", "{% if %}", "{{ 1 + }}", "{{ 5 | no_such_filter }}"]:
            with pytest.raises(TemplateSyntaxError):
                render_template(text, {})

    def test_inner_templates_are_rendered_first(self):
        # GIVEN
        template_vars = {"page": 3, "p3b1": {"x": 40}}

        # THEN
        assert render_template("{{ p{{ page }}b1.x }}", template_vars) == "40"
        assert render_template("{{ p{{ page }}b1.x + 2 }}", template_vars) == "42"

    def test_several_inner_templates(self):
        # GIVEN
        template_vars = {"page": 1, "p1b21": {"x": 10, "w": 5}}

        # THEN
        assert (
            render_template("{{ (p{{ page }}b21.x | int) + (p{{ page }}b21.w | int) }}", template_vars) == "15"
        )

    def test_inner_templates_that_make_up_the_outer_one(self):
        # GIVEN
        template_vars = {"B": "1", "C": "2"}

        # THEN
        assert render_template("{{ {{ B }}{{ C }} }}", template_vars) == "12"

    def test_inner_templates_in_text_with_several_templates(self):
        # GIVEN
        template_vars = {"a": "A", "b": "B", "c": "C", "d": "D"}

        # THEN
        assert render_template("{{ a }} {{ b }} {{ c }}", template_vars) == "A B C"
        assert render_template("{{ a }} {{ b }} {{ c }} {{ d }}", template_vars) == "A B C D"
        assert render_template("x {{ a }} y", template_vars) == "x A y"

    def test_inner_templates_with_unknown_variables(self):
        # the inner template stays as it is, which makes the outer one invalid
        with pytest.raises(TemplateSyntaxError):
            render_template("{{ p{{ page }}b1.x }}", {})

    def test_inner_templates_only_work_in_a_single_outer_template(self):
        # known limitation: the inner templates are found in the text without its first and last two characters, which
        # is the inside of the outer template only if the text is that one template (see TODO.md)
        # GIVEN
        template_vars = {"n": 1, "a": "A", "p1b1": {"x": 40}}

        # THEN: works
        assert render_template("{{ p{{ n }}b1.x }} px", template_vars) == "40 px"
        assert render_template("{{ p{{ n }}b{{ n }}.x }}", template_vars) == "40"

        # THEN: text before the template, and several templates with inner templates
        for text in ["x {{ p{{ n }}b1.x }}", "{{ a }} {{ p{{ n }}b1.x }}", "{{ p{{ n }}b1.x }} {{ p{{ n }}b1.x }}"]:
            with pytest.raises(TemplateSyntaxError):
                render_template(text, template_vars)

    def test_a_template_that_is_only_inner_templates_in_braces(self):
        # the inner template is the whole inside: nothing is rendered ahead, Jinja2 rejects the braces
        with pytest.raises(TemplateSyntaxError):
            render_template("{{{{ B }}}}", {"B": 1})

    def test_inner_templates_in_strict_mode(self):
        # GIVEN
        template_vars = {"page": 3, "p3b1": {"x": 40}}

        # THEN
        assert render_template("{{ p{{ page }}b1.x }}", template_vars, strict=True) == "40"
        with pytest.raises(UndefinedError):
            render_template("{{ p{{ nope }}b1.x }}", template_vars, strict=True)

    def test_inner_templates_over_several_lines(self):
        # GIVEN
        template_vars = {"n": 2, "p2b1": {"x": 7}}

        # THEN
        assert render_template("{{ p{{ n }}b1.x\n + 1 }}", template_vars) == "8"

    def test_the_same_template_renders_with_different_variables(self):
        # THEN (compiled templates are cached by their text)
        assert render_template("{{ a }}", {"a": 1}) == "1"
        assert render_template("{{ a }}", {"a": 2}) == "2"
        assert render_template("{{ a }}", {"a": 1}, strict=True) == "1"
        with pytest.raises(UndefinedError):
            render_template("{{ a }}", {}, strict=True)
        assert render_template("{{ a }}", {}) == "{{ a }}"


class TestCheckTemplate(TestBase):
    def test_a_template_that_renders(self):
        # THEN
        assert check_template("{{ a }}", {"a": 1}) is None
        assert check_template("plain", {}) is None
        assert check_template("{{ p{{ page }}b1.x }}", {"page": 1, "p1b1": {"x": 1}}) is None

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


class TestHasUnresolvedVariables(TestBase):
    def test_text_with_unknown_variables(self):
        # THEN
        assert has_unresolved_variables("{{ nope }}") is True
        assert has_unresolved_variables("a {{ obj.nope }} b") is True
        assert has_unresolved_variables("{{ p1b2.x + 1 }}") is True

    def test_text_that_is_not_a_valid_template(self):
        # THEN
        assert has_unresolved_variables("{{ unclosed") is True

    def test_resolved_values(self):
        # THEN
        assert has_unresolved_variables("plain") is False
        assert has_unresolved_variables("") is False
        assert has_unresolved_variables("{{ 1 }}") is False
        assert has_unresolved_variables("100%") is False

    def test_values_that_are_not_text(self):
        # THEN
        for value in [1, 1.5, True, None, ["{{ nope }}"], {"a": "{{ nope }}"}]:
            assert has_unresolved_variables(value) is False


class TestReferencedVariables(TestBase):
    def test_variables_of_templates(self):
        # THEN
        assert referenced_variables("{{ about.title }}") == {"about"}
        assert referenced_variables('{"text": "{{ about.title }}", "x": "{{ p1b1.x + offset }}"}') == {"about", "p1b1", "offset"}
        assert referenced_variables("{% if night %}{{ a }}{% endif %}") == {"night", "a"}
        assert referenced_variables("no templates") == set()
        assert referenced_variables("") == set()

    def test_text_that_can_not_be_parsed_as_a_whole(self):
        # THEN: the expressions that can be parsed count
        assert referenced_variables('{"a": "{{ title }}", "b": "{{ broken", "c": "{% if night %}x{% endif %}"}') >= {"title"}
        assert referenced_variables("{{ a }} and {{ b ") == {"a"}

    def test_nested_templates(self):
        # THEN: the variables of the inner templates are found, the outer one can't be parsed
        assert referenced_variables("{{ (p{{ page }}b21.x | int) + (p{{ other }}b21.w | int) }}") == {"page", "other"}
        assert referenced_variables("{{ p{{ common.pages.index }}b1.x }} {{ title }}") == {"common", "title"}

    def test_expressions_that_can_not_be_parsed_are_skipped(self):
        # THEN
        assert referenced_variables("{{ 1 + }} {{ ok }} {% if %}") == {"ok"}


class TestRenderDictRecursive(TestBase):
    def test_render_dict_recursively__template_rendering_works(self):
        # GIVEN
        input_data = {"{{ key }}": "{{ value }}"}
        template_vars = {"key": "key_rendered", "value": "value_rendered"}

        # WHEN
        result = render_dict_recursive(input=input_data, template_vars=template_vars)

        # THEN
        assert result == {"key_rendered": "value_rendered"}

    def test_render_dict_recursively__two_step_rendering(self):
        # GIVEN
        input_data = {
            "A": "B",
            "B": "{{ A }}",
            "C": "{{ B }}",
        }

        template_vars = {}

        # WHEN
        result = render_dict_recursive(input=input_data, template_vars=template_vars)

        # THEN
        assert result == {"A": "B", "B": "B", "C": "B"}

    def test_render_dict_recursively__inner_template(self):
        # GIVEN
        input_data = {
            "A": "{{ {{ B }}{{ C }} }}",
            "B": "1",
            "C": "2",
        }

        template_vars = {}

        # WHEN
        result = render_dict_recursive(input=input_data, template_vars=template_vars)

        # THEN
        assert result == {
            "A": "12",
            "B": "1",
            "C": "2",
        }

    def test_render_dict_recursively__global_vars(self):
        # GIVEN
        input_data = {
            "A": "{{ header.bar.item_y }}",
        }

        template_vars = {"header": {"bar": {"height": 27, "item_y": "0.5%"}}}

        # WHEN
        result = render_dict_recursive(input=input_data, template_vars=template_vars)

        # THEN
        assert result == {
            "A": "0.5%",
        }

    def test_render_dict_recursively__template_in_list_item(self):
        # GIVEN
        input_data = {
            "key": [
                "{{ variable }}",
            ]
        }

        template_vars = {"variable": "value"}

        # WHEN
        result = render_dict_recursive(input=input_data, template_vars=template_vars)

        # THEN
        assert result == {
            "key": ["value"],
        }

    def test_the_template_variables_are_not_changed(self):
        # GIVEN
        template_vars = {"v": "1", "nested": {"a": "x"}}

        # WHEN
        render_dict_recursive({"A": "{{ v }}", "nested": {"b": "{{ nested.a }}"}}, template_vars)

        # THEN
        assert template_vars == {"v": "1", "nested": {"a": "x"}}

    def test_the_input_is_not_changed(self):
        # GIVEN
        input_data = {"A": "{{ v }}", "L": ["{{ v }}"], "D": {"x": "{{ v }}"}}

        # WHEN
        render_dict_recursive(input_data, {"v": "1"})

        # THEN
        assert input_data == {"A": "{{ v }}", "L": ["{{ v }}"], "D": {"x": "{{ v }}"}}

    def test_values_that_are_not_text_are_kept(self):
        # GIVEN
        input_data = {"i": 1, "f": 1.5, "b": False, "n": None}

        # THEN
        assert render_dict_recursive(input_data, {}) == input_data

    def test_lists_may_contain_values_that_are_not_text(self):
        # GIVEN
        input_data = {"k": [1, "{{ v }}", None, True, 2.5]}

        # THEN
        assert render_dict_recursive(input_data, {"v": "x"}) == {"k": [1, "x", None, True, 2.5]}

    def test_entries_can_be_used_before_they_are_defined(self):
        # GIVEN
        input_data = {"C": "{{ B }}", "B": "{{ A }}", "A": "1"}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"A": "1", "B": "1", "C": "1"}

    def test_nested_dicts(self):
        # GIVEN
        input_data = {"outer": {"inner": "{{ v }}", "deeper": {"x": "{{ v }}!"}}}

        # THEN
        assert render_dict_recursive(input_data, {"v": "1"}) == {"outer": {"inner": "1", "deeper": {"x": "1!"}}}

    def test_entries_of_a_nested_dict_can_use_each_other_and_the_dict_can_be_used_later(self):
        # GIVEN
        input_data = {"a": {"x": "1", "y": "{{ a.x }}{{ a.x }}"}, "b": "{{ a.y }}"}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"a": {"x": "1", "y": "11"}, "b": "11"}

    def test_keys_with_templates_in_nested_dicts(self):
        # GIVEN
        input_data = {"{{ k }}": {"{{ k }}2": "{{ v }}"}}

        # THEN
        assert render_dict_recursive(input_data, {"k": "key", "v": "val"}) == {"key": {"key2": "val"}}

    def test_a_nested_dict_does_not_see_entries_that_come_later(self):
        # a nested dict is rendered once: what it can't resolve then is left out (a known limitation)
        # GIVEN
        input_data = {"a": {"x": "{{ top }}"}, "top": "1"}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"a": {}, "top": "1"}

    def test_text_with_braces_can_not_be_a_value(self, capsys):
        # known limitation: "{{" in a rendered value counts as an unresolved template
        # WHEN
        result = render_dict_recursive({"A": "{{ '{{' }}", "B": "ok"}, {})

        # THEN
        assert result == {"B": "ok"}
        assert "No progression" in capsys.readouterr().out

    def test_entries_that_never_resolve_are_left_out_and_reported(self, capsys):
        # GIVEN
        input_data = {"A": "{{ nope }}", "B": "ok", "L": ["{{ nope }}"]}

        # WHEN
        result = render_dict_recursive(input_data, {})

        # THEN
        assert result == {"B": "ok"}
        assert "No progression while rendering templates" in capsys.readouterr().out

    def test_entries_that_refer_to_each_other_are_left_out(self, capsys):
        # WHEN
        result = render_dict_recursive({"A": "{{ B }}", "B": "{{ A }}", "C": "c"}, {})

        # THEN
        assert result == {"C": "c"}
        assert "No progression" in capsys.readouterr().out

    def test_a_key_that_never_resolves_is_left_out(self, capsys):
        # WHEN
        result = render_dict_recursive({"{{ nope }}": 1, "ok": 2}, {})

        # THEN
        assert result == {"ok": 2}
        assert "No progression" in capsys.readouterr().out

    def test_a_key_that_can_not_be_rendered_is_reported(self, capsys):
        # WHEN
        result = render_dict_recursive({"{{ unclosed": 1, "ok": 2}, {})

        # THEN
        assert result == {"ok": 2}
        assert "Can't render the key '{{ unclosed'" in capsys.readouterr().out

    def test_a_value_that_can_not_be_rendered_is_left_out(self):
        # WHEN
        result = render_dict_recursive({"A": "{{ unclosed", "L": ["{{ unclosed"], "ok": "1"}, {})

        # THEN
        assert result == {"ok": "1"}

    def test_a_value_can_resolve_after_a_failed_attempt(self):
        # `{{ later.x }}` raises while `later` is unknown, and renders when it is defined
        # GIVEN
        input_data = {"A": "{{ later.x }}", "later": {"x": "1"}}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"A": "1", "later": {"x": "1"}}

    def test_object_properties_like_the_deployment_uses_them(self):
        # GIVEN: objects by name, referring to each other and to variables
        input_data = {
            "p1b1": {"page": 1, "id": 1, "x": 10, "w": 20},
            "p1b2": {"page": 1, "id": 2, "x": "{{ (p1b1.x | int) + (p1b1.w | int) }}", "text": "{{ about.title }}"},
            "p1b3": {"page": 1, "id": 3, "y": "{{ p{{ page }}b2.x }}"},
        }

        # WHEN
        result = render_dict_recursive(input_data, {"about": {"title": "T"}, "page": 1})

        # THEN
        assert result["p1b2"] == {"page": 1, "id": 2, "x": "30", "text": "T"}
        assert result["p1b3"]["y"] == "30"
