import pytest
from jinja2 import TemplateRuntimeError, TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from openhasp_config_manager.processing import template_rendering
from openhasp_config_manager.processing.template_rendering import (
    TemplateRenderError,
    check_template,
    evaluate_template,
    is_single_template,
    object_variables,
    referenced_variables,
    render_variables,
    render_dict_recursive,
    render_template,
    render_template_collecting_unknown,
    has_nested_templates,
    referenced_objects,
    render_nested_templates,
    render_template_or_keep,
    template_spans,
    template_syntax_error,
)
from tests import TestBase


class TestRenderTemplate(TestBase):
    def test_text_without_templates_is_unchanged(self):
        for text in ["", "x", "plain text", "run L:/page.jsonl", "100%", 'it\'s "quoted"', "a } b { c"]:
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
        assert render_template("{{ obj['name'] }}", template_vars) == "n"
        assert render_template("{{ x | default('d') }} {% if y is defined %}y{% else %}no y{% endif %}", {}) == "d no y"

    def test_unknown_variables_stay_as_they_are_written(self):
        # THEN
        assert render_template("{{ nope }}", {}) == "{{ nope }}"
        assert render_template("a {{ nope }} b {{ known }}", {"known": 1}) == "a {{ nope }} b 1"

    def test_an_unknown_key_of_a_dict_stays_too(self):
        # THEN
        assert render_template("{{ obj.nope }}", {"obj": {}}) == "{{ nope }}"
        assert render_template("{{ obj['nope'] }}", {"obj": {}}) == "{{ nope }}"

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

    def test_braces_can_be_written_as_text(self):
        # THEN
        assert render_template("{{ '{{' }}", {}) == "{{"
        assert render_template("{{ '}}' }}", {}) == "}}"
        assert render_template("{{ '{{ x }}' }}", {}) == "{{ x }}"
        assert render_template('{{ "it\'s" }}', {}) == "it's"
        assert render_template(r"{{ 'it\'s' }}", {}) == "it's"

    def test_dict_literals_in_templates(self):
        # THEN
        assert render_template("{{ {'a': 1}['a'] }}", {}) == "1"
        assert render_template("{{ {'a': {'b': 2}}['a']['b'] }}", {}) == "2"

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
        assert render_template("{{ (p{{ page }}b21.x | int) + (p{{ page }}b21.w | int) }}", template_vars) == "15"
        assert render_template("{{ p{{ page }}b{{ page }}.x }}", {"page": 1, "p1b1": {"x": 7}}) == "7"

    def test_inner_templates_that_make_up_the_outer_one(self):
        # GIVEN
        template_vars = {"B": "1", "C": "2"}

        # THEN
        assert render_template("{{ {{ B }}{{ C }} }}", template_vars) == "12"
        assert render_template("{{{{ B }}}}", template_vars) == "1"

    def test_inner_templates_next_to_text_and_other_templates(self):
        # GIVEN
        template_vars = {"n": 1, "a": "A", "p1b1": {"x": 40}}

        # THEN
        assert render_template("{{ p{{ n }}b1.x }} px", template_vars) == "40 px"
        assert render_template("x {{ p{{ n }}b1.x }}", template_vars) == "x 40"
        assert render_template("{{ a }} {{ p{{ n }}b1.x }}", template_vars) == "A 40"
        assert render_template("{{ p{{ n }}b1.x }} {{ p{{ n }}b1.x }}", template_vars) == "40 40"
        assert render_template("{{ a }} {{ p{{ n }}b1.x }} {{ a }} {{ p{{ n }}b1.x + 1 }}!", template_vars) == "A 40 A 41!"

    def test_deeper_nesting(self):
        # GIVEN
        template_vars = {"a": "b", "b": "c", "c": 7}

        # THEN
        assert render_template("{{ {{ {{ a }} }} }}", template_vars) == "7"
        assert render_template("{{ {{ a }} }}", template_vars) == "c"

    def test_inner_templates_over_several_lines(self):
        # GIVEN
        template_vars = {"n": 2, "p2b1": {"x": 7}}

        # THEN
        assert render_template("{{ p{{ n }}b1.x\n + 1 }}\n{{ n }}", template_vars) == "8\n2"
        assert render_template("{{ p{{\n n\n }}b1.x }}", template_vars) == "7"

    def test_quotes_in_text_around_templates(self):
        # THEN
        assert render_template("it's {{ p{{ n }}b1.x }} o'clock", {"n": 1, "p1b1": {"x": 4}}) == "it's 4 o'clock"

    def test_inner_templates_with_unknown_variables(self):
        # the inner template stays as it is, which makes the outer one invalid
        with pytest.raises(TemplateSyntaxError):
            render_template("{{ p{{ page }}b1.x }}", {})

    def test_inner_templates_in_strict_mode(self):
        # GIVEN
        template_vars = {"page": 3, "p3b1": {"x": 40}}

        # THEN
        assert render_template("{{ p{{ page }}b1.x }}", template_vars, strict=True) == "40"
        with pytest.raises(UndefinedError):
            render_template("{{ p{{ nope }}b1.x }}", template_vars, strict=True)

    def test_templates_that_are_not_closed(self):
        # THEN
        for text in ["{{ p{{ n }}b1.x", "{{ {{ n }}", "{{ 'unclosed }}", "{{ n }} {{"]:
            with pytest.raises(TemplateSyntaxError):
                render_template(text, {"n": 1})

    def test_the_same_template_renders_with_different_variables(self):
        # THEN (compiled templates are cached by their text)
        assert render_template("{{ a }}", {"a": 1}) == "1"
        assert render_template("{{ a }}", {"a": 2}) == "2"
        assert render_template("{{ a }}", {"a": 1}, strict=True) == "1"
        with pytest.raises(UndefinedError):
            render_template("{{ a }}", {}, strict=True)
        assert render_template("{{ a }}", {}) == "{{ a }}"


class TestKeysAndMethods(TestBase):
    def test_a_key_wins_over_the_method_of_a_dict(self):
        # GIVEN
        template_vars = {"cfg": {"values": 1, "keys": 2, "get": 3, "items": 4, "update": 5, "pop": 6, "copy": 7}}

        # THEN
        for key, value in template_vars["cfg"].items():
            assert render_template("{{ cfg." + key + " }}", template_vars) == str(value)

    def test_the_methods_of_a_dict_without_such_a_key(self):
        # GIVEN
        template_vars = {"cfg": {"a": 1, "b": 2}}

        # THEN
        assert render_template("{% for k, v in cfg.items() %}{{ k }}={{ v }};{% endfor %}", template_vars) == "a=1;b=2;"
        assert render_template("{{ cfg.keys() | list | join(',') }}", template_vars) == "a,b"
        assert render_template("{{ cfg.get('c', 'default') }}", template_vars) == "default"

    def test_keys_that_start_with_an_underscore(self):
        # THEN
        assert render_template("{{ cfg._hidden }}", {"cfg": {"_hidden": "h"}}) == "h"

    def test_attributes_of_objects(self):
        # GIVEN
        class Device:
            name = "plate"

        # THEN
        assert render_template("{{ device.name }}", {"device": Device()}) == "plate"
        assert render_template("{{ device.nope }}", {"device": Device()}) == "{{ nope }}"


class TestSandbox(TestBase):
    def test_python_internals_are_not_reachable(self):
        # THEN: they raise, or render as unknown variables
        for text in [
            "{{ ''.__class__ }}",
            "{{ ''.__class__.__mro__[1].__subclasses__() }}",
            "{{ cycler.__init__.__globals__ }}",
            "{{ lipsum.__globals__ }}",
            "{{ x.__class__ }}",
        ]:
            try:
                result = render_template(text, {"x": 1})
            except (SecurityError, UndefinedError):
                continue
            assert result.startswith("{{"), f"{text} -> {result}"

    def test_containers_can_not_be_changed(self):
        # THEN
        with pytest.raises(SecurityError):
            render_template("{% set _ = cfg.update({'a': 2}) %}", {"cfg": {"a": 1}})
        with pytest.raises(SecurityError):
            render_template("{% set _ = items.append(1) %}", {"items": []})

    def test_huge_ranges_are_refused(self):
        # THEN
        with pytest.raises(OverflowError):
            render_template("{{ range(10000000) | list | length }}", {})


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

    def test_a_nested_dict_can_use_entries_that_come_later(self):
        # GIVEN
        input_data = {"a": {"x": "{{ top }}", "deeper": {"y": "{{ top }}{{ top }}"}}, "top": "1"}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"a": {"x": "1", "deeper": {"y": "11"}}, "top": "1"}

    def test_entries_of_nested_dicts_that_depend_on_each_other_across_dicts(self):
        # GIVEN
        input_data = {"a": {"x": "{{ b.y }}"}, "b": {"y": "{{ c.z }}"}, "c": {"z": "end"}}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"a": {"x": "end"}, "b": {"y": "end"}, "c": {"z": "end"}}

    def test_text_with_braces_can_be_a_value(self):
        # WHEN
        result = render_dict_recursive({"A": "{{ '{{' }}", "B": "{{ A }}!"}, {})

        # THEN
        assert result == {"A": "{{", "B": "{{!"}

    def test_entries_that_never_resolve_are_left_out_and_reported(self, capsys):
        # GIVEN
        input_data = {"A": "{{ nope }}", "B": "ok", "L": ["{{ other }}", "x"]}

        # WHEN
        result = render_dict_recursive(input_data, {})

        # THEN
        assert result == {"B": "ok"}
        output = capsys.readouterr().out
        assert "Can't render these templates: " in output
        assert "A (uses unknown nope)" in output
        assert "L (uses unknown other)" in output

    def test_what_is_resolved_of_a_nested_dict_is_kept_and_the_rest_reported(self, capsys):
        # WHEN
        result = render_dict_recursive({"a": {"ok": "1", "bad": "{{ nope }}"}, "{{ nope }}": 1}, {})

        # THEN
        assert result == {"a": {"ok": "1"}}
        output = capsys.readouterr().out
        assert "a.bad (uses unknown nope)" in output
        assert "{{ nope }} (the key uses unknown nope)" in output

    def test_entries_that_refer_to_each_other_are_left_out(self, capsys):
        # WHEN
        result = render_dict_recursive({"A": "{{ B }}", "B": "{{ A }}", "C": "c"}, {})

        # THEN
        assert result == {"C": "c"}
        assert "Can't render these templates" in capsys.readouterr().out

    def test_a_property_of_something_that_is_not_defined_is_reported(self, capsys):
        # WHEN
        result = render_dict_recursive({"A": "{{ nope.x }}", "B": "ok"}, {})

        # THEN
        assert result == {"B": "ok"}
        assert "A (can't be rendered: 'nope' is undefined)" in capsys.readouterr().out

    def test_a_property_can_resolve_when_its_variable_is_defined_later(self):
        # GIVEN
        input_data = {"A": "{{ later.x }}", "later": {"x": "1"}}

        # THEN
        assert render_dict_recursive(input_data, {}) == {"A": "1", "later": {"x": "1"}}

    def test_an_invalid_template_is_an_error_naming_the_entry(self):
        # THEN
        with pytest.raises(TemplateRenderError, match=r"Invalid template in 'A': .*\{\{ unclosed"):
            render_dict_recursive({"ok": "1", "A": "{{ unclosed"}, {})
        with pytest.raises(TemplateRenderError, match=r"Invalid template in 'outer.inner'"):
            render_dict_recursive({"outer": {"inner": "{{ 1 + }}"}}, {})
        with pytest.raises(TemplateRenderError, match=r"Invalid template in 'L'"):
            render_dict_recursive({"L": ["fine", "{% if %}"]}, {})
        with pytest.raises(TemplateRenderError, match=r"Invalid template in '\{\{ unclosed'"):
            render_dict_recursive({"{{ unclosed": 1}, {})

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


class TestObjectsThatReferToEachOther(TestBase):
    """The objects are in the variables themselves (like a deployment does it), and refer to each other."""

    def test_references_to_templates_later_in_the_dict_wait_for_them(self):
        # GIVEN: a chain of references to objects later in the dict, without calculations
        objects = {
            "p1b1": {"x": "{{ p1b2.x }}"},
            "p1b2": {"x": "{{ p1b3.x }}"},
            "p1b3": {"x": "{{ base }}"},
        }

        # WHEN
        result = render_dict_recursive(objects, {"base": 7, **objects})

        # THEN: nothing uses the text of a template that is not resolved yet
        assert result == {"p1b1": {"x": "7"}, "p1b2": {"x": "7"}, "p1b3": {"x": "7"}}

    def test_a_property_that_uses_a_later_property_of_the_same_object(self):
        # GIVEN
        objects = {"p1b1": {"w": "{{ p1b1.h }}", "h": "{{ size }}", "list": ["{{ p1b1.h }}"]}}

        # WHEN
        result = render_dict_recursive(objects, {"size": 5, **objects})

        # THEN
        assert result == {"p1b1": {"w": "5", "h": "5", "list": ["5"]}}

    def test_references_in_a_cycle_are_left_out_and_reported(self, capsys):
        # GIVEN
        objects = {"p1b1": {"x": "{{ p1b2.x }}", "y": 1}, "p1b2": {"x": "{{ p1b1.x }}"}}

        # WHEN
        result = render_dict_recursive(objects, objects)

        # THEN
        assert result == {"p1b1": {"y": 1}, "p1b2": {}}
        assert "p1b1.x (uses unknown p1b2.x)" in capsys.readouterr().out

    def test_templates_that_are_not_in_the_variables(self):
        # GIVEN: the variables have only a part of the objects
        objects = {"p1b1": {"x": "{{ a }}"}, "p1b2": {"x": "{{ a }}"}, "p1b3": {"x": {"y": "{{ a }}"}}}

        # WHEN
        result = render_dict_recursive(objects, {"a": 1, "p1b1": {}})

        # THEN
        assert result == {"p1b1": {"x": "1"}, "p1b2": {"x": "1"}, "p1b3": {"x": {"y": "1"}}}

    def test_resolved_values_are_converted_before_others_use_them(self):
        # GIVEN
        objects = {"p1b1": {"w": "{{ 10 * 2 }}", "nested": {"a": "1"}}, "p1b2": {"w": "{{ p1b1.w - 5 }}"}}
        calls = []

        def convert(keys, value):
            calls.append(keys)
            return int(value) if keys[-1] == "w" else value

        # WHEN
        result = render_dict_recursive(objects, objects, convert=convert)

        # THEN
        assert result == {"p1b1": {"w": 20, "nested": {"a": "1"}}, "p1b2": {"w": 15}}
        assert ["p1b1", "nested", "a"] in calls and ["p1b1", "nested"] not in calls


class TestThisAndObjectsOfThePage(TestBase):
    def test_the_names_of_an_object(self):
        # GIVEN
        objects = {"p3b4": {"x": 1}, "p3b45": {"h": 2}, "p4b4": {"x": 3}, "other": {"x": 4}}

        # WHEN
        result = object_variables("p3b45", objects)

        # THEN
        assert result == {"this": {"h": 2}, "b4": {"x": 1}, "b45": {"h": 2}}
        assert result["this"] is objects["p3b45"]

    def test_an_object_that_is_not_in_the_variables_and_names_that_are_no_objects(self):
        # THEN
        assert object_variables("p3b9", {"p3b4": {"x": 1}}) == {"b4": {"x": 1}}
        assert object_variables("{{ page }}", {"p3b4": {"x": 1}}) == {}

    def test_objects_refer_to_themselves_and_to_their_page(self):
        # GIVEN: `this` and `bY` before what they use is resolved, also later in the dict
        objects = {
            "p3b1": {"page": 3, "id": 1, "w": "{{ this.h }}", "h": "{{ (b2.h | int) * 2 }}", "text": "Page {{ this.page }}"},
            "p3b2": {"page": 3, "id": 2, "h": "{{ size }}"},
            "p4b2": {"page": 4, "id": 2, "h": 100},
        }

        # WHEN
        result = render_dict_recursive(objects, {"size": 5, **objects}, entry_vars=object_variables)

        # THEN
        assert result["p3b1"] == {"page": 3, "id": 1, "w": "10", "h": "10", "text": "Page 3"}

    def test_the_names_are_only_there_while_the_entry_is_rendered(self):
        # GIVEN: variables with the same names, which the objects hide
        objects = {"p1b1": {"x": "{{ this.y }}", "y": 1}}
        template_vars = {"this": {"y": "variable"}, "b1": "variable", "after": "{{ this }}"}

        # WHEN
        result = render_dict_recursive(
            {**objects, "after": "{{ this.y }}", "b": "{{ b1 }}"}, {**template_vars, **objects}, entry_vars=object_variables
        )

        # THEN
        assert result == {"p1b1": {"x": "1", "y": 1}, "after": "variable", "b": "variable"}

    def test_an_object_whose_name_is_a_template(self):
        # GIVEN
        objects = {"p{{ page }}b1": {"w": "{{ this.h }}", "h": 3}}

        # WHEN
        result = render_dict_recursive(objects, {"page": 2, **objects}, entry_vars=object_variables)

        # THEN
        assert result == {"p2b1": {"w": "3", "h": 3}}

    def test_objects_named_without_their_page(self):
        # THEN
        assert referenced_objects("{{ b2.x + p1b3.y }} {{ this.w }}", {}, page=4) == {"p4b2", "p1b3"}
        assert referenced_objects("{{ b2.x }}", {}) == set()
        assert referenced_objects("{{ p1b2.x }}", {}, page=4) == {"p1b2"}


class TestRenderTemplateOrKeep(TestBase):
    def test_renders_like_render_template(self):
        assert render_template_or_keep("{{ a + 1 }}", {"a": 1}) == "2"
        assert render_template_or_keep("{{ nope }}", {}) == "{{ nope }}"

    def test_keeps_text_that_cannot_use_an_unknown_variable(self):
        assert render_template_or_keep("{{ p3b20.y + 5 }}", {}) == "{{ p3b20.y + 5 }}"

    def test_other_errors_are_raised(self):
        with pytest.raises(TemplateSyntaxError):
            render_template_or_keep("{{ a +", {})
        with pytest.raises(ZeroDivisionError):
            render_template_or_keep("{{ 1 // 0 }}", {})


class TestRenderNestedTemplates(TestBase):
    def test_only_the_inner_templates_are_rendered(self):
        assert render_nested_templates("{{ p{{ page }}b2.x }}", {"page": 3}) == "{{ p3b2.x }}"

    def test_text_without_nested_templates_stays(self):
        assert render_nested_templates("{{ a }} and {{ b }}", {"a": 1}) == "{{ a }} and {{ b }}"


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


class TestEvaluateTemplate(TestBase):
    def test_a_single_template_is_the_value_of_its_expression(self):
        # GIVEN
        template_vars = {"a": 2, "cfg": {"x": [1, 2]}}

        # THEN
        assert evaluate_template("{{ a * 2 }}", template_vars) == 4
        assert evaluate_template(" {{ a / 4 }} ", template_vars) == 0.5
        assert evaluate_template("{{ cfg }}", template_vars) == {"x": [1, 2]}
        assert evaluate_template("{{ cfg.x }}", template_vars) == [1, 2]
        assert evaluate_template("{{ 'text' }}", template_vars) == "text"
        assert evaluate_template("{{ a > 1 }}", template_vars) is True
        assert list(evaluate_template("{{ range(1, 3) }}", template_vars)) == [1, 2]

    def test_a_single_template_with_templates_inside(self):
        # THEN
        assert evaluate_template("{{ p{{ page }}b1 }}", {"page": 3, "p3b1": {"x": 4}}) == {"x": 4}

    def test_other_text_is_text_or_a_number(self):
        # GIVEN
        template_vars = {"a": 2}

        # THEN
        assert evaluate_template("a{{ a }}", template_vars) == "a2"
        assert evaluate_template("1{{ a }}", template_vars) == 12
        assert evaluate_template("{{ a }}.5", template_vars) == 2.5
        assert evaluate_template("-{{ a }}", template_vars) == -2
        assert evaluate_template("{{ a }}{{ a }}", template_vars) == 22
        assert evaluate_template("{% if a %}yes{% endif %}", template_vars) == "yes"
        assert evaluate_template("plain", template_vars) == "plain"

    def test_unknown_variables_are_errors(self):
        # THEN
        with pytest.raises(UndefinedError):
            evaluate_template("{{ nope }}", {})
        with pytest.raises(UndefinedError):
            evaluate_template("{{ cfg.nope }}", {"cfg": {}})
        with pytest.raises(UndefinedError):
            evaluate_template("a {{ nope }}", {})

    def test_invalid_templates(self):
        # THEN
        with pytest.raises(TemplateSyntaxError):
            evaluate_template("{{ 1 + }}", {})
        with pytest.raises(TemplateSyntaxError):
            evaluate_template("{{ 1", {})

    def test_single_templates(self):
        # THEN
        assert is_single_template("{{ a }}") and is_single_template("  {{ a }}\n") and is_single_template("{{ p{{ a }}b1 }}")
        assert not is_single_template("{{ a }}{{ b }}")
        assert not is_single_template("x {{ a }}")
        assert not is_single_template("{{ a")
        assert not is_single_template("{% if a %}{% endif %}")


class TestRenderVariables(TestBase):
    def test_values_are_computed_from_other_values(self):
        # GIVEN: in an order that is not the order they depend on each other
        variables = {
            "card": {"x": "{{ common.margin }}", "w": "{{ device.screen.width - card.x * 2 }}"},
            "common": {"margin": 4, "double": "{{ common.margin * 2 }}"},
            "title": "Page {{ common.double }}",
        }
        device = {"screen": {"width": 320}}

        # WHEN
        result = render_variables(variables, {"device": device})

        # THEN
        assert result == {"card": {"x": 4, "w": 312}, "common": {"margin": 4, "double": 8}, "title": "Page 8"}
        assert "device" not in result
        assert variables["card"]["x"] == "{{ common.margin }}"

    def test_a_value_uses_everything_below_a_name(self):
        # GIVEN
        variables = {"sizes": {"a": "{{ 1 + 1 }}", "b": 3}, "total": "{{ sizes.a + sizes['b'] }}", "all": "{{ sizes }}"}

        # THEN
        assert render_variables(variables) == {"sizes": {"a": 2, "b": 3}, "total": 5, "all": {"a": 2, "b": 3}}

    def test_a_value_below_a_computed_value(self):
        # GIVEN: `items` is computed, and `first` uses a part of it
        variables = {"items": "{{ [10, 20] }}", "first": "{{ items[0] }}"}

        # THEN
        assert render_variables(variables) == {"items": [10, 20], "first": 10}

    def test_templates_in_lists(self):
        # THEN
        assert render_variables({"a": 1, "list": ["x{{ a }}", 2, {"b": "{{ a + 1 }}"}]}) == {
            "a": 1,
            "list": ["x1", 2, {"b": 2}],
        }

    def test_variables_without_templates_stay(self):
        # GIVEN
        variables = {"a": 1, "b": {"c": "text", "d": [1, "x"]}, 5: "five"}

        # THEN
        assert render_variables(variables) == variables

    def test_the_context_wins_and_replaced_values_are_not_computed(self):
        # GIVEN: `card.x` is replaced by the context, its template would fail
        variables = {"card": {"x": "{{ nope }}", "w": "{{ card.x * 2 }}"}, "list": ["{{ nope }}"]}

        # WHEN
        result = render_variables(variables, {"card": {"x": 5}, "list": [1]})

        # THEN
        assert result["card"]["w"] == 10
        assert result["list"] == ["{{ nope }}"]

    def test_jinja_functions_and_local_names(self):
        # THEN
        assert render_variables({"a": "{{ range(3) | list }}"}) == {"a": [0, 1, 2]}
        assert render_variables({"a": [1, 2], "b": "{% for i in a %}{{ i.real }}{% endfor %}"})["b"] == 12
        assert render_variables({"a": {"k": 1}, "b": "{{ a[a.keys() | first] }}"})["b"] == 1

    def test_templates_inside_of_templates(self):
        # GIVEN
        variables = {"n": 1, "item1": "one", "chosen": "{{ item{{ n }} }}"}

        # THEN
        assert render_variables(variables)["chosen"] == "one"

    def test_a_name_built_by_a_template_inside_must_be_computed_already(self):
        # GIVEN: the dependency on `item1` can't be seen, and it is computed after `chosen`
        variables = {"chosen": "{{ item{{ n }} }}", "n": 1, "item1": "{{ 'one' }}"}

        # THEN
        with pytest.raises(TemplateRenderError, match=r"Can't compute the variable 'chosen': 'item1' is not computed yet"):
            render_variables(variables)

    def test_cycles_are_errors(self):
        # THEN
        with pytest.raises(TemplateRenderError, match=r"cycle: a -> b -> a$"):
            render_variables({"a": "{{ b }}", "b": "{{ a }}"})
        with pytest.raises(TemplateRenderError, match=r"cycle: x.y -> x.y$"):
            render_variables({"x": {"y": "{{ x.y + 1 }}"}})
        with pytest.raises(TemplateRenderError, match=r"cycle: x.y -> x.y$"):
            render_variables({"x": {"y": "{{ x }}"}})

    def test_unknown_names_are_errors(self):
        # THEN
        with pytest.raises(TemplateRenderError, match=r"Unknown variable 'nope' in the variable 'a.b': \{\{ nope \+ 1 \}\}"):
            render_variables({"a": {"b": "{{ nope + 1 }}"}})
        with pytest.raises(TemplateRenderError, match=r"Unknown variable 'a.nope' in the variable 'b'"):
            render_variables({"a": {"c": 1}, "b": "{{ a.nope.x }}"})
        with pytest.raises(TemplateRenderError, match=r"Unknown variable 'p1b2' in the variable 'b'"):
            render_variables({"b": "{{ p1b2.x }}"})

    def test_a_name_below_something_that_is_not_a_mapping(self):
        # THEN: the rendering tells
        with pytest.raises(TemplateRenderError, match=r"Can't compute the variable 'b'"):
            render_variables({"a": [1], "b": "{{ a.nope }}"})

    def test_invalid_templates_and_other_errors(self):
        # THEN
        with pytest.raises(TemplateRenderError, match=r"Invalid template: .*: \{\{ 1 \+ \}\}"):
            render_variables({"a": "{{ 1 + }}"})
        with pytest.raises(TemplateRenderError, match=r"Can't compute the variable 'a': division by zero"):
            render_variables({"a": "{{ 1 / 0 }}"})
        with pytest.raises(TemplateRenderError, match=r"Invalid template: No filter named 'no_such_filter'"):
            render_variables({"a": "{{ 1 | no_such_filter }}"})

    def test_raw_text_is_not_rendered(self):
        # THEN
        assert render_variables({"a": "{% raw %}{{ x }}{% endraw %}"}) == {"a": "{{ x }}"}


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
