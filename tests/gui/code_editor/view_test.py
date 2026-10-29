
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QContextMenuEvent, QTextCursor  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.source.syntax import Language  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.editor import CodeEditor  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.code_editor.helpers import _type  # noqa: E402


MULTILINE = '{\n  "page": 1,\n  "id": 1,\n  "text": "a"\n}\n{"page": 1, "id": 2, "parentid": 1}\n'


class TestSearch(TestBase):
    def test_find_next_wraps(self, editor):
        editor.set_text("ab AB ab")
        assert editor.search.set_search("ab")
        assert editor.search.find_next()
        assert editor.textCursor().selectionStart() == 0
        editor.search.find_next()
        editor.search.find_next()
        editor.search.find_next()
        assert editor.textCursor().selectionStart() == 0
        editor.search.find_next(forward=False)
        assert editor.textCursor().selectionStart() == 6

    def test_options(self, editor):
        editor.set_text("ab AB abc")
        editor.search.set_search("ab", case_sensitive=True)
        assert len(editor.extraSelections()) == 2  # two matches
        editor.search.set_search("ab", whole_word=True)
        assert len(editor.extraSelections()) == 2
        editor.search.set_search("a.", regex=True)
        assert len(editor.extraSelections()) == 3
        assert not editor.search.set_search("(", regex=True)
        assert not editor.search.find_next()
        assert editor.search.set_search("")
        assert not editor.search.find_next()

    def test_no_match(self, editor):
        editor.set_text("abc")
        editor.search.set_search("zzz")
        assert not editor.search.find_next()
        assert not editor.search.find_next(forward=False)

    def test_replace(self, editor):
        editor.set_text("a1 a2 a3")
        editor.search.set_search(r"a(\d)", regex=True)
        editor.search.find_next()
        assert editor.search.replace_current(r"b\1\1")
        assert editor.toPlainText() == "b11 a2 a3"
        assert editor.search.replace_all("x")
        assert editor.toPlainText() == "b11 x x"
        assert not editor.search.replace_current("y")

    def test_replace_without_search(self, editor):
        assert editor.search.replace_all("x") == 0
        assert not editor.search.replace_current("x")


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
        # the "not closed" marker, no brackets
        assert len(editor.extraSelections()) == 1

    def test_matching_brackets_over_several_lines(self, editor):
        # GIVEN
        editor.set_text(MULTILINE)
        editor.go_to(5, 0)

        # WHEN
        marked = [(s.cursor.blockNumber(), s.cursor.positionInBlock()) for s in editor.extraSelections() if s.cursor.hasSelection()]

        # THEN the bracket after the cursor and its partner (the selection ends after the bracket)
        assert marked == [(4, 1), (0, 1)]

    def test_matching_brackets_follow_typing(self, editor):
        editor.set_text('{"a": 1}\n{"b": 2}')
        editor.go_to(2, 0)
        selections = len(editor.extraSelections())
        # an unbalanced `[` in the first object pairs with nothing: the brackets of the second object are still marked
        editor.go_to(1, 5)
        _type(editor, "[")
        editor.go_to(2, 0)
        assert len(editor.extraSelections()) == selections


class TestFolding(TestBase):
    def test_fold_hides_the_lines_between_the_brackets(self, editor):
        editor.set_text(MULTILINE)
        assert editor.folding.ranges() == [(1, 5)]

        assert editor.folding.fold(1)

        document = editor.document()
        assert [document.findBlockByNumber(n).isVisible() for n in range(6)] == [True, False, False, False, True, True]
        assert editor.folding.is_folded(1)
        assert editor.folding.unfold(1)
        assert all(document.findBlockByNumber(n).isVisible() for n in range(6))
        assert not editor.folding.fold(6)  # one line, nothing to fold
        editor.grab()

    def test_toggle_and_all(self, editor):
        editor.set_text(MULTILINE + MULTILINE)
        editor.folding.fold_all()
        assert editor.folding.is_folded(1) and editor.folding.is_folded(7)
        editor.folding.unfold_all()
        assert not editor.folding.is_folded(1)
        assert editor.folding.toggle(7)
        assert editor.folding.is_folded(7)

    def test_fold_and_unfold_at_cursor(self, editor):
        editor.set_text(MULTILINE)
        editor.go_to(3, 2)
        editor.folding.fold_at_cursor()
        assert editor.folding.is_folded(1)
        assert editor.cursor_line_column[0] == 1  # the cursor was in the hidden lines
        editor.folding.unfold_at_cursor()
        assert not editor.folding.is_folded(1)

    def test_keys(self, editor):
        editor.set_text(MULTILINE)
        editor.go_to(2, 0)
        QTest.keyClick(editor, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        assert editor.folding.is_folded(1)
        QTest.keyClick(editor, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        assert not editor.folding.is_folded(1)
        QTest.keyClick(editor, Qt.Key.Key_Underscore, Qt.KeyboardModifier.ControlModifier)
        assert editor.folding.is_folded(1)
        QTest.keyClick(editor, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        assert not editor.folding.is_folded(1)

    def test_cursor_moving_into_a_fold_opens_it(self, editor):
        editor.set_text(MULTILINE)
        editor.folding.fold(1)
        editor.go_to(3, 0)
        assert not editor.folding.is_folded(1)

    def test_clicking_the_gutter(self, editor):
        editor.set_text(MULTILINE)
        QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=QPoint(5, 10))
        assert editor.folding.is_folded(1)
        QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=QPoint(5, 10))
        assert not editor.folding.is_folded(1)
        # a line without an object that can be folded, and below the text
        QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=QPoint(5, editor.fontMetrics().height() * 5 + 10))
        QTest.mouseClick(editor.gutter, Qt.MouseButton.LeftButton, pos=QPoint(5, 290))
        assert editor.folding._folded == set()

    def test_editing_the_line_count_unfolds(self, editor):
        editor.set_text(MULTILINE)
        editor.folding.fold(1)
        editor.go_to(1, 1)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert not editor.folding.is_folded(1)

    def test_other_languages_have_nothing_to_fold(self, qapp, settings):
        yaml = CodeEditor(Language.YAML)
        yaml.set_text(MULTILINE)
        assert yaml.folding.ranges() == []


class TestObjectAtCursor(TestBase):
    def test_signal_follows_the_cursor(self, editor):
        editor.set_text(MULTILINE)
        found = []
        editor.cursorObjectChanged.connect(found.append)
        editor.go_to(3, 0)
        editor.go_to(4, 0)  # the same object: no signal
        editor.go_to(6, 0)
        editor.go_to(1, 0)
        assert found == [1, 0]
        assert editor.object_at_cursor().index == 0
        editor.set_text("")
        assert editor.object_at_cursor() is None

    def test_object_at_cursor_follows_typing(self, editor):
        # GIVEN
        editor.set_text(MULTILINE)
        found = []
        editor.cursorObjectChanged.connect(found.append)
        editor.go_to(6, 0)

        # WHEN a new object is opened before the second one, in its own line (typing would close it)
        editor.textCursor().insertText("{\n")

        # THEN the cursor is in the new object: it isn't closed, so it reaches over the second one to the last line
        assert (editor.object_at_cursor().start_line, editor.object_at_cursor().end_line) == (6, 8)
        assert editor.folding.ranges() == [(1, 5), (6, 8)]
        # closed before the second one, on its line
        editor.textCursor().insertText("}")
        editor.go_to(6, 0)
        assert (editor.object_at_cursor().start_line, editor.object_at_cursor().end_line) == (6, 7)
        assert editor.folding.ranges() == [(1, 5)]
        editor.go_to(7, 0)
        assert editor.object_at_cursor().index == 1
        assert editor.objects()[2].start_line == 7
        editor.go_to(8, 0)
        assert editor.object_at_cursor() is None
        editor.go_to(2, 0)
        assert editor.object_at_cursor().index == 0
        assert found == [1, -1, 0]

    def test_object_at_cursor_in_a_nested_object(self, editor):
        editor.set_text('{"a": 1}\n{\n  "b": {\n    "c": [\n      1\n    ]\n  }\n}\n')
        editor.go_to(5, 0)
        found = editor.object_at_cursor()
        assert (found.index, found.start_line, found.end_line) == (1, 2, 8)
        assert found.get("b").value_end_line == 7


class TestFormatAndRename(TestBase):
    def test_format_document_is_one_undo_step(self, editor):
        editor.set_text('{\n"a": 1,   \n    "b": 2\n}')
        editor.go_to(3, 4)
        assert editor.edits.format_document()
        assert editor.toPlainText() == '{\n  "a": 1,\n  "b": 2\n}\n'
        assert not editor.edits.format_document()
        editor.undo()
        assert editor.toPlainText() == '{\n"a": 1,   \n    "b": 2\n}'

    def test_format_with_the_keys(self, editor):
        editor.set_text('{\n"a": 1\n}')
        QTest.keyClick(editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        assert editor.toPlainText() == '{\n  "a": 1\n}\n'

    def test_rename_id(self, editor):
        editor.set_text(MULTILINE)
        editor.go_to(2, 0)
        assert editor.edits.object_id == 1
        assert editor.edits.rename_id(7) is None
        assert editor.toPlainText() == MULTILINE.replace('"id": 1,', '"id": 7,').replace('"parentid": 1', '"parentid": 7')
        assert editor.cursor_line_column[0] == 2

    def test_rename_reports_why_not(self, editor):
        editor.set_text(MULTILINE)
        editor.go_to(2, 0)
        assert "already used" in editor.edits.rename_id(2)
        editor.go_to(6, 0)
        editor.set_text("// nothing")
        assert editor.edits.object_id is None
        assert "no object" in editor.edits.rename_id(2)

    def test_rename_key(self, editor):
        requests = []
        editor.renameRequested.connect(lambda: requests.append(1))
        QTest.keyClick(editor, Qt.Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
        assert requests == [1]

    def test_context_menu_actions(self, editor, monkeypatch):
        from PyQt6.QtWidgets import QMenu

        shown = []
        monkeypatch.setattr(
            QMenu, "exec", lambda menu, position=None: shown.append([a.text() for a in menu.actions() if a.text()])
        )
        editor.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5)))
        assert any(text.startswith("Format document") for text in shown[0])
        assert any(text.startswith("Fold all") for text in shown[0])
