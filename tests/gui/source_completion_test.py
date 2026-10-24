from openhasp_config_manager.gui.domain.source_completion import CompletionContext, complete, completion_context
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
        assert complete(context) == ["bg_color", "bg_color02"]

    def test_variables_exclude_the_typed_word(self):
        context = CompletionContext("variable", "a.b", 0)
        assert complete(context, variables=["a.b", "a.bc", "a.c", "x"]) == ["a.bc"]
