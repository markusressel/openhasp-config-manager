
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.source.issues import SourceIssue  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.code_editor.helpers import _type


def _move_to(editor, line, column):
    editor.go_to(line, column)


class TestText(TestBase):
    def test_set_text_is_no_edit(self, editor):
        edits = []
        editor.textEdited.connect(lambda: edits.append(1))
        editor.set_text('{"a": 1}\n{"b": 2}')
        assert edits == []
        _type(editor, "x")
        assert edits

    def test_set_text_keeps_the_cursor(self, editor):
        editor.set_text("one\ntwo\nthree")
        _move_to(editor, 2, 2)
        editor.set_text("one\ntwo!\nthree")
        assert editor.cursor_line_column == (2, 3)
        editor.set_text("one")
        assert editor.cursor_line_column[0] == 1
        editor.set_text("one")  # same text: nothing happens

    def test_go_to_beyond_the_end_goes_to_the_last_line(self, editor):
        editor.set_text("a\nb")
        editor.go_to(99)
        assert editor.cursor_line_column[0] == 2

    def test_issues_are_found(self, editor):
        editor.set_text('{"page": }')
        assert [(m.line, m.severity) for m in editor.issues] == [(1, Severity.ERROR)]
        editor.set_app_markers([SourceIssue(1, 0, 1, Severity.WARNING, "outside")])
        assert len(editor.extraSelections()) >= 3
        editor.set_text('{"page": 1}')
        assert editor.issues == []

    def test_issues_are_updated_after_typing(self, editor):
        issues = []
        editor.issuesChanged.connect(lambda: issues.append(1))
        _type(editor, "{")
        QTest.qWait(500)
        assert issues


class TestTyping(TestBase):
    def test_brackets_and_quotes_are_closed(self, editor):
        _type(editor, '{"a')
        assert editor.toPlainText() == '{"a"}'

    def test_closing_character_is_typed_over(self, editor):
        _type(editor, '{"a"}')
        assert editor.toPlainText() == '{"a"}'

    def test_backspace_removes_the_pair(self, editor):
        _type(editor, "[")
        QTest.keyClick(editor, Qt.Key.Key_Backspace)
        assert editor.toPlainText() == ""

    def test_no_pair_in_front_of_a_word(self, editor):
        editor.set_text("word")
        editor.go_to(1, 0)
        _type(editor, "{")
        assert editor.toPlainText() == "{word"

    def test_selection_is_wrapped(self, editor):
        editor.set_text("abc")
        editor.selectAll()
        _type(editor, '"')
        assert editor.toPlainText() == '"abc"'

    def test_enter_keeps_the_indentation(self, editor):
        editor.set_text("  a")
        editor.go_to(1, 3)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert editor.toPlainText() == "  a\n  "

    def test_enter_between_brackets_opens_a_block(self, editor):
        _type(editor, "{")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert editor.toPlainText() == "{\n  \n}"
        assert editor.cursor_line_column == (2, 3)

    def test_tab_indents_to_the_next_stop(self, editor):
        editor.set_text("a")
        editor.go_to(1, 1)
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        assert editor.toPlainText() == "a "
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        assert editor.toPlainText() == "a   "

    def test_tab_and_backtab_on_lines(self, editor):
        editor.set_text("a\n\nb")
        editor.selectAll()
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        assert editor.toPlainText() == "  a\n\n  b"
        QTest.keyClick(editor, Qt.Key.Key_Backtab)
        assert editor.toPlainText() == "a\n\nb"
        QTest.keyClick(editor, Qt.Key.Key_Backtab)
        assert editor.toPlainText() == "a\n\nb"

    def test_comment_and_duplicate(self, editor):
        editor.set_text('{"a": 1}\n{"b": 2}')
        editor.go_to(1)
        QTest.keyClick(editor, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
        assert editor.toPlainText() == '// {"a": 1}\n{"b": 2}'
        QTest.keyClick(editor, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
        assert editor.toPlainText() == '{"a": 1}\n{"b": 2}'
        QTest.keyClick(editor, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        assert editor.toPlainText() == '{"a": 1}\n{"a": 1}\n{"b": 2}'

    def test_shortcuts_emit_signals(self, editor):
        events = []
        editor.saveRequested.connect(lambda: events.append("save"))
        editor.findRequested.connect(lambda: events.append("find"))
        QTest.keyClick(editor, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert events == ["save", "find"]


class TestCompletion(TestBase):
    def test_property_names(self, editor):
        _type(editor, '{"bg_c')
        assert editor.completion.completer.popup().isVisible()
        assert editor.completion.completer.completionCount() == 1
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText().startswith('{"bg_color')

    def test_a_key_is_completed_before_its_quote(self, editor):
        editor.set_text('{\n  "obj": "slider",\n  ')
        editor.go_to(3, 3)
        _type(editor, "va")
        assert editor.completion.completer.popup().isVisible()
        assert "val" in editor.completion.completer.model().stringList()
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText().endswith('  "val": ')
        assert editor.textCursor().position() == len(editor.toPlainText())

    def test_text_values_start_inside_their_quotes(self, editor):
        editor.set_text("{\n  ")
        editor.go_to(2, 3)
        _type(editor, "alig")
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText() == '{\n  "align": ""'
        _type(editor, "left")
        assert editor.toPlainText() == '{\n  "align": "left"'

    def test_the_quote_that_was_closed_for_us_is_not_doubled(self, editor):
        _type(editor, '{"alig')
        assert editor.toPlainText() == '{"alig"}'
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText() == '{"align": ""}'
        _type(editor, "left")
        assert editor.toPlainText() == '{"align": "left"}'

    def test_the_values_of_a_property(self, editor):
        editor.set_text('{"obj": "label", "mode": "')
        editor.go_to(1, 27)
        _type(editor, "d")
        popup = editor.completion.completer.popup()
        assert popup.isVisible()
        assert editor.completion.completer.currentCompletion() == "dots"
        QTest.keyClick(popup, Qt.Key.Key_Return)
        assert editor.toPlainText() == '{"obj": "label", "mode": "dots"'

    def test_the_values_show_after_a_property_is_chosen(self, editor):
        editor.set_text('{"obj": "label", ')
        editor.go_to(1, 18)
        _type(editor, '"mod')
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText() == '{"obj": "label", "mode": ""'
        QTest.qWait(50)
        assert editor.completion.completer.popup().isVisible()
        assert editor.completion.completer.model().stringList()[:3] == ["expand", "break", "dots"]

    def test_nothing_before_the_quote_outside_of_objects(self, editor):
        editor.set_text("")
        _type(editor, "alig")
        assert not editor.completion.completer.popup().isVisible()

    def test_variables(self, editor):
        editor.completion.set_variables(lambda: ["theme.navbar.height", "theme.name", "other"])
        editor.set_text('{"text": "{{ ')
        editor.go_to(1, 13)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert editor.completion.completer.popup().isVisible()
        assert editor.completion.completer.completionCount() == 3
        _type(editor, "the")
        assert editor.completion.completer.completionCount() == 2

    def test_only_the_properties_of_the_type_of_the_object(self, editor):
        editor.set_text('{"obj": "slider", "page": 1,\n "')
        editor.go_to(2, 2)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        words = set(editor.completion.completer.model().stringList())
        assert {"val", "min", "bg_color"} <= words
        assert not {"text", "options", "obj", "page"} & words  # not of a slider, or there already

    def test_explanation_of_the_highlighted_entry_next_to_the_list(self, editor):
        editor.resize(900, 400)
        editor.set_text('{"obj": "slider", "va')
        editor.go_to(1, 21)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        popup = editor.completion.completer.popup()
        card = editor.completion.card
        assert popup.isVisible() and card.isVisible()
        assert card._name.text() == "val" and "current value" in card._body.toPlainText()
        assert card._kind.text() == "slider property"
        popup.hide()
        assert not card.isVisible()

    def test_explanation_follows_the_highlighted_entry(self, editor):
        editor.resize(900, 400)
        editor.set_text('{"obj": "slider", "m')
        editor.go_to(1, 20)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        first = editor.completion.card._name.text()
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Down)
        assert editor.completion.card._name.text() != first

    def test_no_explanation_without_room_next_to_the_list(self, editor):
        editor.resize(300, 400)
        editor.set_text('{"obj": "slider", "va')
        editor.go_to(1, 21)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert editor.completion.completer.popup().isVisible()
        assert not editor.completion.card.isVisible()

    def test_no_explanation_for_variables(self, editor):
        editor.completion.set_variables(lambda: ["theme.name"])
        editor.set_text('{"text": "{{ ')
        editor.go_to(1, 13)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert editor.completion.completer.popup().isVisible()
        assert not editor.completion.card.isVisible()

    def test_placeholders_in_a_text(self, editor):
        editor.resize(900, 400)
        _type(editor, '{"obj": "label", "text": "%')
        popup = editor.completion.completer.popup()
        assert popup.isVisible() and editor.completion.completer.completionCount() == 6
        _type(editor, "ho")
        assert editor.completion.completer.completionCount() == 1
        assert editor.completion.card.isVisible() and editor.completion.card._name.text() == "%hostname%"
        QTest.keyClick(popup, Qt.Key.Key_Return)
        assert editor.toPlainText() == '{"obj": "label", "text": "%hostname%"}'
        assert editor.textCursor().positionInBlock() == len('{"obj": "label", "text": "%hostname%')

    def test_no_placeholders_in_other_properties(self, editor):
        _type(editor, '{"w": "%')
        assert not editor.completion.completer.popup().isVisible()

    def test_nothing_to_complete(self, editor):
        _type(editor, "zzz")
        assert not editor.completion.completer.popup().isVisible()
