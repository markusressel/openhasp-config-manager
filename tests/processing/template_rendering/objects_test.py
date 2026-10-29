
import pytest

from openhasp_config_manager.processing.template_rendering import (
    TemplateRenderError,
    object_variables,
    render_dict_recursive,
    referenced_objects,
)
from tests import TestBase


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
