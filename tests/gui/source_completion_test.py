from openhasp_config_manager.gui.domain.source_completion import (
    CompletionContext,
    complete,
    completion_context,
    properties_for,
)
from openhasp_config_manager.gui.domain.source_docs import property_help
from openhasp_config_manager.gui.domain.source_syntax import Language
from tests import TestBase


class TestContext(TestBase):
    def test_property_at_the_start_of_an_object(self):
        assert completion_context('{"te', Language.JSONL) == CompletionContext("property", "te", 2)
        assert completion_context('  "', Language.JSONL) == CompletionContext("property", "", 3)
        assert completion_context('{"a": 1, "x', Language.JSONL) == CompletionContext("property", "x", 10)

    def test_no_property_inside_values(self):
        assert completion_context('{"text": "ab', Language.JSONL) is None
        assert completion_context('{"text": "ab"', Language.JSONL) is None
        assert completion_context('{"text', Language.YAML) is None

    def test_variable_inside_a_template(self):
        assert completion_context('{"text": "{{ theme.na', Language.JSONL) == CompletionContext("variable", "theme.na", 13)
        assert completion_context("run {{ ", Language.CMD) == CompletionContext("variable", "", 7)
        assert completion_context("a: {{ x | int + b", Language.YAML) == CompletionContext("variable", "b", 16)

    def test_closed_template_asks_for_nothing(self):
        assert completion_context('{"text": "{{ a }} ', Language.JSONL) is None

    def test_other_files(self):
        assert completion_context("x", Language.TEXT) is None
        assert completion_context("run ", Language.CMD) is None


class TestComplete(TestBase):
    def test_properties(self):
        context = CompletionContext("property", "bg_c", 0)
        assert complete(context) == ["bg_color"]

    def test_variables_exclude_the_typed_word(self):
        context = CompletionContext("variable", "a.b", 0)
        assert complete(context, variables=["a.b", "a.bc", "a.c", "x"]) == ["a.bc"]


class TestProperties(TestBase):
    def test_documented_properties_are_completed(self):
        from openhasp_config_manager.gui.domain.source_completion import OBJECT_PROPERTIES
        from openhasp_config_manager.gui.domain.source_docs import PROPERTY_DOCS

        assert set(PROPERTY_DOCS) <= set(OBJECT_PROPERTIES)
        assert "tag" in complete(CompletionContext("property", "ta", 1))


class TestPropertiesOfType(TestBase):
    def test_only_the_properties_that_make_sense(self):
        slider = properties_for("slider")
        assert {"val", "min", "max", "start_value", "bg_color", "x", "tag"} <= set(slider)
        assert not {"text", "options", "toggle", "src"} & set(slider)
        assert {"text", "toggle", "mode", "align"} <= set(properties_for("btn"))
        assert {"options", "rows"} <= set(properties_for("roller"))
        assert "rows" not in properties_for("btn")

    def test_unknown_types_get_everything(self):
        everything = properties_for(None)
        assert everything == properties_for("{{ some.template }}")
        assert {"val", "text", "options", "src", "bg_color", "prev"} <= set(everything)

    def test_part_and_state_are_offered_once_a_style_property_is_typed(self):
        assert "bg_color10" not in properties_for("slider", "bg_c")
        assert {"bg_color", "bg_color00", "bg_color02", "bg_color10", "bg_color25"} <= set(
            properties_for("slider", "bg_color")
        )
        assert "bg_color12" in complete(CompletionContext("property", "bg_color1", 0), properties_for("slider", "bg_color1"))

    def test_only_the_parts_of_the_type(self):
        offered = properties_for("switch", "bg_color")
        assert "bg_color10" in offered and "bg_color20" in offered
        assert "bg_color30" not in offered

    def test_present_properties_are_not_offered_again(self):
        assert "bg_color" not in properties_for("btn", present=["bg_color", "text"])
        assert "text" not in properties_for("btn", present=["bg_color", "text"])
        assert "radius" in properties_for("btn", present=["bg_color", "text"])

    def test_every_offered_property_is_explained(self):
        for object_type in ("btn", "slider", "arc", "gauge", "tabview", "img", None):
            for name in properties_for(object_type):
                assert property_help(name, object_type) is not None, (object_type, name)
