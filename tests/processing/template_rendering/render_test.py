
import pytest
from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from openhasp_config_manager.processing.template_rendering import (
    evaluate_template,
    is_single_template,
    render_template,
    render_nested_templates,
    render_template_or_keep,
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
