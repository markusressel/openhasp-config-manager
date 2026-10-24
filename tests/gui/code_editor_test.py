import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QTextCursor  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.source_syntax import Language  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor import CodeEditor, Marker  # noqa: E402
from tests import TestBase  # noqa: E402


@pytest.fixture
def editor(qapp, settings):
    widget = CodeEditor(Language.JSONL)
    widget.resize(500, 300)
    widget.show()
    yield widget
    widget.close()


def _type(editor, text):
    QTest.keyClicks(editor, text)


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
        editor.set_app_markers([Marker(1, 0, 1, Severity.WARNING, "outside")])
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
        assert editor._completer.popup().isVisible()
        assert editor._completer.completionCount() == 2
        QTest.keyClick(editor._completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText().startswith('{"bg_color')

    def test_variables(self, editor):
        editor.set_variables(lambda: ["theme.navbar.height", "theme.name", "other"])
        editor.set_text('{"text": "{{ ')
        editor.go_to(1, 13)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert editor._completer.popup().isVisible()
        assert editor._completer.completionCount() == 3
        _type(editor, "the")
        assert editor._completer.completionCount() == 2

    def test_nothing_to_complete(self, editor):
        _type(editor, "zzz")
        assert not editor._completer.popup().isVisible()


class TestSearch(TestBase):
    def test_find_next_wraps(self, editor):
        editor.set_text("ab AB ab")
        assert editor.set_search("ab")
        assert editor.find_next()
        assert editor.textCursor().selectionStart() == 0
        editor.find_next()
        editor.find_next()
        editor.find_next()
        assert editor.textCursor().selectionStart() == 0
        editor.find_next(forward=False)
        assert editor.textCursor().selectionStart() == 6

    def test_options(self, editor):
        editor.set_text("ab AB abc")
        editor.set_search("ab", case_sensitive=True)
        assert len(editor.extraSelections()) == 3  # current line + two matches
        editor.set_search("ab", whole_word=True)
        assert len(editor.extraSelections()) == 3
        editor.set_search("a.", regex=True)
        assert len(editor.extraSelections()) == 4
        assert not editor.set_search("(", regex=True)
        assert not editor.find_next()
        assert editor.set_search("")
        assert not editor.find_next()

    def test_no_match(self, editor):
        editor.set_text("abc")
        editor.set_search("zzz")
        assert not editor.find_next()
        assert not editor.find_next(forward=False)

    def test_replace(self, editor):
        editor.set_text("a1 a2 a3")
        editor.set_search(r"a(\d)", regex=True)
        editor.find_next()
        assert editor.replace_current(r"b\1\1")
        assert editor.toPlainText() == "b11 a2 a3"
        assert editor.replace_all("x")
        assert editor.toPlainText() == "b11 x x"
        assert not editor.replace_current("y")

    def test_replace_without_search(self, editor):
        assert editor.replace_all("x") == 0
        assert not editor.replace_current("x")


class TestAppearance(TestBase):
    def test_zoom_and_options(self, editor):
        size = editor.font().pointSize()
        editor.zoom(2)
        assert editor.font().pointSize() == size + 2
        editor.reset_zoom()
        assert editor.font().pointSize() == 10
        editor.set_word_wrap(True)
        editor.set_word_wrap(False)
        editor.set_show_whitespace(True)
        editor.set_show_whitespace(False)
        editor.set_text('{"a": 1}\n' * 200)
        editor.refresh_theme()
        editor.grab()
        assert editor.gutter_width() > 20

    def test_matching_brackets_are_marked(self, editor):
        editor.set_text('{"a": [1]}')
        editor.go_to(1, 5)
        before = len(editor.extraSelections())
        editor.go_to(1, 0)
        assert len(editor.extraSelections()) == before + 2
        editor.go_to(1, 5)
        assert len(editor.extraSelections()) == before
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        assert len(editor.extraSelections()) == before + 2
        editor.set_text("{")
        editor.go_to(1, 0)
        # the current line and the "not closed" marker, no brackets
        assert len(editor.extraSelections()) == 2
