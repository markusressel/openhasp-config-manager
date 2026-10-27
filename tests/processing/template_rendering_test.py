import pytest
from jinja2 import TemplateRuntimeError, TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from openhasp_config_manager.processing import template_rendering
from openhasp_config_manager.processing.template_rendering import (
    TemplateRenderError,
    check_template,
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
