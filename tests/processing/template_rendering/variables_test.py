import gc
import weakref

import pytest
from jinja2 import TemplateError, TemplateSyntaxError

from openhasp_config_manager.processing.template_rendering import (
    TemplateRenderError,
    render_variables,
    render_template,
    render_template_collecting_unknown,
    render_template_or_keep,
)
from tests import TestBase


class _Held:
    """Stands for something a caller holds while it renders, e.g. the QPainter of a paint event."""


class TestRenderVariables(TestBase):
    def test_values_that_use_a_missing_name_stay_as_they_are(self):
        # GIVEN: `device` is not known, `card.h` uses it through `card.w`
        variables = {
            "margin": 4,
            "card": {"w": "{{ device.screen.width - margin * 2 }}", "h": "{{ card.w // 2 }}"},
            "x": "{{ margin }}",
        }

        # WHEN
        result = render_variables(variables, missing=frozenset({"device"}))

        # THEN
        assert result == {"margin": 4, "card": variables["card"], "x": 4}

    def test_an_unknown_name_that_is_not_missing_still_raises(self):
        with pytest.raises(TemplateRenderError, match="Unknown variable 'nope'"):
            render_variables({"a": "{{ device.x + nope }}"}, missing=frozenset({"device"}))

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


class TestErrorsReleaseTheCallers:
    """A template error must not keep the frames of the code that rendered it (and their locals) alive until the next GC."""

    @staticmethod
    def _locals_of_caller_survive(render) -> bool:
        def caller():
            held = _Held()
            try:
                render()
            except TemplateError:
                pass
            return weakref.ref(held)

        gc.disable()
        try:
            ref = caller()
            return ref() is not None
        finally:
            gc.enable()

    def test_an_unknown_variable_that_is_kept_as_written(self):
        assert render_template_or_keep("{{ p3b20.y + 5 }}", {}) == "{{ p3b20.y + 5 }}"
        assert not self._locals_of_caller_survive(lambda: render_template_or_keep("{{ p3b20.y + 5 }}", {}))

    def test_an_error_that_is_raised(self):
        # GIVEN: an unknown filter, which is an error at compile time; an unknown variable in strict mode, at render time
        assert not self._locals_of_caller_survive(lambda: render_template_or_keep("{{ 1 | nope }}", {}))
        assert not self._locals_of_caller_survive(lambda: render_template_collecting_unknown("{{ 1 | nope }}", {}))
        assert not self._locals_of_caller_survive(lambda: render_template("{{ a.b }}", {}, strict=True))

    def test_syntax_errors_still_know_the_template(self):
        with pytest.raises(TemplateSyntaxError) as raised:
            render_template("{{ a +  }}", {})
        assert raised.value.source == "{{ a +  }}"
        assert raised.value.translated
