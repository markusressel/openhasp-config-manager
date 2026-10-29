import pytest

from openhasp_config_manager.gui.domain.source.completion import (
    CompletionContext,
    Insertion,
    complete,
    completion_context,
    placeholder_insertion,
    properties_for,
    property_insertion,
    value_choice,
    value_insertion,
    value_words,
)
from openhasp_config_manager.gui.domain.object_type_docs import is_text_property
from openhasp_config_manager.gui.domain.source.docs import property_help
from openhasp_config_manager.gui.domain.source.syntax import Language
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
        assert completion_context('  "name": "{{ a', Language.JSON) is None


class TestComplete(TestBase):
    def test_properties(self):
        context = CompletionContext("property", "bg_c", 0)
        assert complete(context) == ["bg_color"]

    def test_variables_exclude_the_typed_word(self):
        context = CompletionContext("variable", "a.b", 0)
        assert complete(context, variables=["a.b", "a.bc", "a.c", "x"]) == ["a.bc"]


class TestProperties(TestBase):
    def test_documented_properties_are_completed(self):
        from openhasp_config_manager.gui.domain.source.completion import OBJECT_PROPERTIES
        from openhasp_config_manager.gui.domain.source.docs import PROPERTY_DOCS

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


class TestKeyWithoutQuotes(TestBase):
    def test_a_key_is_completed_before_its_quote(self):
        def at(line: str):
            return completion_context(line, Language.JSONL, inside_object=True)

        assert at("{al") == CompletionContext("property", "al", 1, quoted=False)
        assert at("  te") == CompletionContext("property", "te", 2, quoted=False)
        assert at('{"a": 1, x') == CompletionContext("property", "x", 9, quoted=False)
        assert at("  ") == CompletionContext("property", "", 2, quoted=False)

    def test_only_inside_of_objects(self):
        assert completion_context("  te", Language.JSONL) is None
        assert completion_context("  te", Language.JSONL, inside_object=False) is None

    def test_not_where_a_value_or_a_comment_is(self):
        def at(line: str):
            return completion_context(line, Language.JSONL, inside_object=True)

        assert at('{"text": al') is None
        assert at('{"text": "a, b') is None
        assert at("// say, al") is None
        assert at('{"src": "http://x", al') == CompletionContext("property", "al", 20, quoted=False)
        assert completion_context("run al", Language.CMD, inside_object=True) is None

    def test_text_values_start_with_their_quotes(self):
        assert is_text_property("align") and is_text_property("text") and is_text_property("src")
        assert is_text_property("bg_color") and is_text_property("bg_color10") and is_text_property("text_color02")
        assert is_text_property("options", "dropdown") and not is_text_property("options", "btnmatrix")
        assert not is_text_property("mode", "roller") and is_text_property("mode", "label")
        assert not is_text_property("x") and not is_text_property("val") and not is_text_property("enabled")


class TestInsertion(TestBase):
    def _insert(self, line: str, column: int, word: str, object_type=None, **context):
        found = completion_context(line[:column], Language.JSONL, inside_object=True)
        insertion = property_insertion(line, column, found, word, object_type)
        return line[: insertion.start] + insertion.text + line[insertion.end :], insertion

    def test_text_gets_the_colon_and_the_quotes_of_the_value(self):
        result, insertion = self._insert('  "al', 5, "align")
        assert result == '  "align": ""'
        assert result[: insertion.cursor] == '  "align": "'

    def test_other_values_get_the_colon(self):
        result, insertion = self._insert('  "va', 5, "val", "slider")
        assert result == '  "val": ' and insertion.cursor == len(result)

    def test_the_quotes_of_the_key_come_with_it(self):
        result, insertion = self._insert("  al", 4, "align")
        assert result == '  "align": ""' and result[: insertion.cursor] == '  "align": "'
        assert self._insert("  va", 4, "val")[0] == '  "val": '

    def test_the_closing_quote_that_is_there_is_not_doubled(self):
        result, insertion = self._insert('{"al"}', 4, "align")
        assert result == '{"align": ""}'
        assert result[: insertion.cursor] == '{"align": "'

    def test_the_rest_of_the_word_is_replaced(self):
        assert self._insert('  "al|ign": "left"'.replace("|", ""), 5, "align")[0] == '  "align": "left"'

    def test_a_key_with_a_value_keeps_it(self):
        result, insertion = self._insert('  "te": 1', 5, "text")
        assert result == '  "text": 1' and insertion == Insertion(3, 6, 'text"', 8)
        assert self._insert("  te : 1", 4, "text")[0] == '  "text" : 1'

    def test_part_and_state_variants_are_text_for_colors(self):
        assert self._insert('  "bg_color1', 12, "bg_color10", "slider")[0] == '  "bg_color10": ""'


class TestPlaceholders(TestBase):
    def test_percent_at_the_start_of_a_text(self):
        assert completion_context('{"text": "%', Language.JSONL) == CompletionContext("placeholder", "%", 10)
        assert completion_context('  "text" : "%ho', Language.JSONL) == CompletionContext("placeholder", "%ho", 12)
        assert completion_context('{"obj": "label", "text": "%', Language.JSONL).kind == "placeholder"

    def test_candidates(self):
        assert complete(CompletionContext("placeholder", "%", 0)) == [
            "%hostname%", "%ip%", "%mac%", "%model%", "%ssid%", "%version%",
        ]  # fmt: skip
        assert complete(CompletionContext("placeholder", "%m", 0)) == ["%mac%", "%model%"]
        assert complete(CompletionContext("placeholder", "%HO", 0)) == ["%hostname%"]
        assert complete(CompletionContext("placeholder", "%foo", 0)) == []

    def test_no_placeholder_elsewhere(self):
        # in the middle of a text (openHASP only replaces a whole text), in other properties, in keys, in templates
        assert completion_context('{"text": "IP %', Language.JSONL) is None
        assert completion_context('{"text": "100%', Language.JSONL) is None
        assert completion_context('{"w": "%', Language.JSONL) is None
        assert completion_context('{"%', Language.JSONL) == CompletionContext("property", "%", 2)
        assert completion_context('{"text": "{{ "%', Language.JSONL).kind == "variable"
        assert completion_context('"text": "%', Language.CMD) is None
        assert completion_context('"text": "%', Language.JSON) is None

    def test_insertion_replaces_what_is_typed(self):
        def insert(line, column, word):
            context = completion_context(line[:column], Language.JSONL)
            insertion = placeholder_insertion(line, column, context, word)
            return line[: insertion.start] + insertion.text + line[insertion.end :], insertion.cursor

        assert insert('{"text": "%ho"}', 13, "%hostname%") == ('{"text": "%hostname%"}', 20)
        assert insert('{"text": "%ho|stn%"}'.replace("|", ""), 13, "%hostname%") == ('{"text": "%hostname%"}', 20)
        assert insert('{"text": "%"}', 11, "%ip%") == ('{"text": "%ip%"}', 14)


class TestValues(TestBase):
    def test_the_start_of_a_value(self):
        assert completion_context('{"obj": "label", "mode": "do', Language.JSONL) == CompletionContext(
            "value", "do", 25, quoted=True, key="mode"
        )
        assert completion_context('  "bg_grad_dir": ', Language.JSONL) == CompletionContext(
            "value", "", 17, quoted=False, key="bg_grad_dir"
        )
        assert completion_context('// "mode": "d', Language.JSONL) is None
        assert completion_context('{"text": "%i', Language.JSONL).kind == "placeholder"

    def test_the_values_of_a_property(self):
        assert value_words("label", "mode") == ["expand", "break", "dots", "scroll", "loop", "crop"]
        assert value_words("cpicker", "mode") == ["hue", "saturation", "value"]
        # the part and state of a style property don't matter
        assert value_words("obj", "bg_grad_dir10") == ["0", "1", "2"]
        assert value_words("line", "line_rounded") == ["true", "false"]
        assert "slider" in value_words(None, "obj")
        # a property that takes more than a few values
        assert value_words("label", "x") == []
        assert value_words("obj", "mode") == []

    def test_candidates_in_their_order_ignoring_case(self):
        context = CompletionContext("value", "", 0, key="align")
        assert complete(context, values=["left", "center", "right", "auto"]) == ["left", "center", "right", "auto"]
        context = CompletionContext("value", "LE", 0, key="align")
        assert complete(context, values=["left", "center", "right", "auto"]) == ["left"]

    def test_the_meaning_of_a_value(self):
        assert value_choice("label", "mode", "dots").meaning.startswith("keep the size, wrap the lines")
        assert value_choice("obj", "bg_grad_dir", "1").value == 1
        assert value_choice("obj", "bg_grad_dir", "7") is None

    @pytest.mark.parametrize(
        "line, column, word, expected",
        [
            # a text gets its quotes, also when it was started without them
            ('{"mode": "do"}', 12, "dots", ('{"mode": "dots"}', 15)),
            ('{"mode": "d|ts"}'.replace("|", ""), 11, "dots", ('{"mode": "dots"}', 15)),
            ('{"mode": ', 9, "dots", ('{"mode": "dots"', 15)),
            # a number or true/false without quotes, unless they were typed
            ('{"bg_grad_dir": ', 16, "1", ('{"bg_grad_dir": 1', 17)),
            ('{"bg_grad_dir": ""}', 17, "1", ('{"bg_grad_dir": "1"}', 19)),
            ('{"line_rounded": t', 18, "true", ('{"line_rounded": true', 21)),
        ],
    )
    def test_insertion(self, line, column, word, expected):
        context = completion_context(line[:column], Language.JSONL)
        choice = value_choice("label", context.key, word)
        insertion = value_insertion(line, column, context, word, choice)
        assert (line[: insertion.start] + insertion.text + line[insertion.end :], insertion.cursor) == expected
