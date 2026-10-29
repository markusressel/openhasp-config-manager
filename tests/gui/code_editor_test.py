from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QContextMenuEvent, QTextCursor, QTextFormat  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.source.syntax import Language  # noqa: E402
from openhasp_config_manager.gui.domain.variables.definitions import Definition  # noqa: E402
from openhasp_config_manager.gui.domain.source.issues import SourceIssue  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.editor import CodeEditor  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor import hover as editor_hover  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.helpers import wait_until  # noqa: E402


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


MULTILINE = '{\n  "page": 1,\n  "id": 1,\n  "text": "a"\n}\n{"page": 1, "id": 2, "parentid": 1}\n'


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


class TestLinksAndDocs(TestBase):
    def test_ctrl_click_on_a_reference(self, qapp, settings):
        editor = CodeEditor(Language.CMD)
        editor.resize(500, 100)
        editor.show()
        editor.set_text("run L:/pages.jsonl\nrun x")
        targets = []
        editor.linkRequested.connect(targets.append)
        position = QPoint(editor.fontMetrics().horizontalAdvance("run L:/pa") + 5, 5)

        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(5, 30))

        assert targets == ["pages.jsonl"]
        editor.close()

    def test_ctrl_click_on_a_part_of_a_variable(self, qapp, settings):
        # GIVEN: only `common.header` is defined
        editor = CodeEditor(Language.JSONL)
        editor.resize(500, 100)
        editor.show()
        editor.set_text('{"h": "{{ common.header.height }}"}')
        known = {"common", "common.header"}
        editor.set_definition_finder(lambda name: Definition(Path("x.yaml"), 1, 0) if name in known else None)
        names = []
        editor.definitionRequested.connect(names.append)
        click = Qt.KeyboardModifier.ControlModifier

        # WHEN
        for prefix in ('{"h": "{{ com', '{"h": "{{ common.hea', '{"h": "{{ common.header.hei'):
            position = QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 2, 5)
            QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, click, position)

        # THEN: the last part has no definition
        assert names == ["common", "common.header"]
        editor.close()

    def test_hovering_with_ctrl_underlines_the_reference(self, qapp, settings):
        editor = CodeEditor(Language.CMD)
        editor.resize(500, 100)
        editor.show()
        editor.set_text("run L:/pages.jsonl")
        position = QPoint(editor.fontMetrics().horizontalAdvance("run L:/pa") + 5, 5)
        before = len(editor.extraSelections())

        QTest.mouseMove(editor.viewport(), position)
        editor._set_hover_link(editor._link_at(position))
        assert len(editor.extraSelections()) == before + 1
        assert editor.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor
        QTest.keyRelease(editor, Qt.Key.Key_Control)
        assert len(editor.extraSelections()) == before
        assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
        editor.close()

    def _position(self, editor, prefix: str, line: int = 0) -> QPoint:
        # the line height of the editor is not the height of its font (it depends on the font of the machine)
        block = editor.blockBoundingGeometry(editor.document().findBlockByNumber(line)).translated(editor.contentOffset())
        return QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 6, int(block.center().y()))

    def _hover(self, editor, position: QPoint):
        # the cursor of the test platform stays where it was, so moving to the same place twice sends no event
        QTest.mouseMove(editor.viewport(), QPoint(450, 250))
        QTest.mouseMove(editor.viewport(), position)

    def test_the_current_line_does_not_hide_the_color_of_a_color_string(self, qapp, settings):
        # GIVEN: a color string in the line of the cursor: it is shown on its color (white), with dark text
        editor = CodeEditor(Language.YAML)
        editor.resize(400, 100)
        editor.show()
        editor.set_text('c: "#ffffff"\n')
        editor.go_to(1, 0)
        qapp.processEvents()

        # WHEN
        image = editor.viewport().grab().toImage()

        # THEN: the string still has its light background, not the dark one of the editor
        block = editor.blockBoundingGeometry(editor.document().firstBlock()).translated(editor.contentOffset())
        x = editor.fontMetrics().horizontalAdvance('c: "#fff') + editor.document().documentMargin()
        assert image.pixelColor(int(x), int(block.top() + 1)).lightness() > 150
        editor.close()

    def test_a_hint_dims_the_text_but_not_a_color_string(self, qapp, settings):
        # GIVEN: an unused variable (a hint) with a color: dimmed text would be white on the white color
        editor = CodeEditor(Language.YAML)
        editor.set_text('  text_color: "#E8EAF0"\n')
        editor.set_hints([SourceIssue(1, 2, 22, Severity.HINT, "unused")])

        # THEN: the key is dimmed, the color string is not
        dimmed = {
            (selection.cursor.selectionStart(), selection.cursor.selectionEnd()): selection.format.hasProperty(
                QTextFormat.Property.ForegroundBrush
            )
            for selection in editor.extraSelections()
        }
        assert dimmed == {(2, 14): True, (14, 23): False}

    def test_hover_card_explains_a_placeholder(self, editor):
        editor.set_text('{"obj": "btn", "text": "%ip%"}')

        content = editor.hover.card_content_at(self._position(editor, '{"obj": "btn", "text": "%i'))

        assert content.help is not None and content.help.name == "%ip%"
        assert "IP address" in content.help.summary
        assert content.help.url == "https://www.openhasp.com/0.7.0/design/data-types/#variables"

    def test_placeholder_has_its_own_color(self, editor):
        from openhasp_config_manager.gui.domain.source.syntax import TokenKind
        from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color

        editor.set_text('{"text": "%ip%"}')
        formats = editor.document().firstBlock().layout().formats()
        color_at = {f.start: f.format.foreground().color() for f in formats}
        assert color_at[len('{"text": "')] == syntax_color(TokenKind.PLACEHOLDER)
        assert syntax_color(TokenKind.PLACEHOLDER) not in (syntax_color(TokenKind.STRING), syntax_color(TokenKind.TEMPLATE))

    def test_hover_card_explains_the_default_properties_of_the_theme(self, qapp, settings):
        yaml_editor = CodeEditor(Language.YAML)
        yaml_editor.resize(500, 200)
        yaml_editor.show()
        yaml_editor.set_text("theme:\n  obj:\n    btn:\n      bg_color04: '#fff'\n")

        content = yaml_editor.hover.card_content_at(self._position(yaml_editor, "      bg_", line=3))

        assert content.help is not None and content.help.name == "bg_color04"
        yaml_editor.close()

    def test_pressing_ctrl_keeps_the_hover_card_so_its_text_can_be_copied(self, editor):
        # GIVEN: the card is shown
        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=2 * editor_hover._HOVER_DELAY_MS + 400)

        # WHEN: Ctrl is pressed in the card (which has the focus after text was selected), and in the editor
        QTest.keyPress(editor.hover.card._body, Qt.Key.Key_Control)
        QTest.keyPress(editor, Qt.Key.Key_Control)

        # THEN
        assert editor.hover.card.isVisible()

        # WHEN: a key that is input
        QTest.keyClick(editor, Qt.Key.Key_X)

        # THEN: the card is gone
        assert not editor.hover.card.isVisible()

    def test_hover_card_shows_after_a_short_delay(self, editor):

        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        assert editor_hover._HOVER_DELAY_MS <= 150
        assert not editor.hover.card.isVisible()
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=2 * editor_hover._HOVER_DELAY_MS + 400)
        assert editor.hover.card._name.text() == "w" and "pixels" in editor.hover.card._body.toPlainText()
        assert editor.hover.card._kind.text() == "Property of every object"
        assert "openhasp.com" in editor.hover.card._link.text()

    def _card_and_property(self, editor, line: int):
        """:return: the rectangles of the card and of the property it is about, in the coordinates of the editor"""
        self._hover(editor, self._position(editor, '{"', line))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        area = editor.hover.tip_area
        return editor.hover.card.geometry(), QRect(editor.viewport().mapTo(editor, area.topLeft()), area.size())

    def test_hover_card_is_above_the_property(self, editor):
        editor.resize(600, 700)
        editor.set_text("\n" * 14 + '{"w": "33%"}')
        card, area = self._card_and_property(editor, 14)
        assert card.bottom() < area.top()
        assert editor.rect().contains(card)

    def test_hover_card_is_below_if_there_is_no_room_above(self, editor):
        editor.resize(600, 700)
        editor.set_text('{"w": "33%"}')
        card, area = self._card_and_property(editor, 0)
        assert card.top() > area.bottom()
        assert editor.rect().contains(card)

    def test_hover_card_never_covers_the_property(self, editor):
        # an editor that is too small for the card above or below: the text of the card gets shorter
        editor.resize(600, 160)
        editor.set_text("\n" * 3 + '{"obj": "switch", "bg_color10": "x"}')
        card, area = self._card_and_property(editor, 3)
        assert not card.intersects(area)

    def test_hover_card_is_not_a_window(self, editor):
        assert not editor.hover.card.isWindow() and editor.hover.card.parentWidget() is editor
        assert not editor.completion.card.isWindow()

    def test_hover_card_stays_while_the_mouse_is_on_it(self, editor):

        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        # the mouse leaves the editor and reaches the card in time
        editor.hover.grace_timer.start()
        editor.hover.card.mouseEntered.emit()
        QTest.qWait(editor_hover._HOVER_GRACE_MS + 100)
        assert editor.hover.card.isVisible()
        # and leaves the card
        editor.hover.card.mouseLeft.emit()
        wait_until(lambda: not editor.hover.card.isVisible(), timeout_ms=editor_hover._HOVER_GRACE_MS + 500)

    def test_hover_card_goes_away_after_the_mouse_left_the_property(self, editor):

        editor.set_text('{"w": "33%", "h": 1}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        self._hover(editor, QPoint(490, 290))
        wait_until(lambda: not editor.hover.card.isVisible(), timeout_ms=editor_hover._HOVER_GRACE_MS + 500)

    def test_hover_card_moves_to_the_next_property(self, editor):
        editor.set_text('{"w": "33%", "h": 1}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible() and editor.hover.card._name.text() == "w", timeout_ms=1000)
        self._hover(editor, self._position(editor, '{"w": "33%", "h'))
        wait_until(lambda: editor.hover.card._name.text() == "h", timeout_ms=1000)
        assert editor.hover.card.isVisible()

    def test_hover_card_goes_away_when_typing_or_clicking(self, editor):
        editor.set_text('{"w": "33%"}')
        for action in (
            lambda: QTest.keyClick(editor, Qt.Key.Key_End),
            lambda: QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(300, 100)),
        ):
            self._hover(editor, self._position(editor, '{"'))
            wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
            action()
            assert not editor.hover.card.isVisible()

    def test_card_content_of_a_property(self, editor):
        text = '{"w": "33%", "nope": 1, "bg_color02": "x"}'
        editor.set_text(text)

        def at(prefix: str):
            return editor.hover.card_content_at(self._position(editor, prefix))

        assert at('{"').help.name == "w" and "pixels" in at('{"').help.summary
        assert at('{"w": "33%", "no').is_empty()  # unknown property
        assert at('{"w": "33%').is_empty()  # a value
        editor.set_text('{"src": "x", "text_color02": 1}')
        assert "`L:/image.png`" in at('{"sr').help.summary
        found = at('{"src": "x", "text_c').help
        assert found.name == "text_color02" and dict(found.details)["State"] == "2: pressed, not toggled"
        editor.set_text('{"obj": "switch", "bg_color10": 1}')
        assert dict(at('{"obj": "switch", "bg_c').help.details)["Part"] == "1: the indicator (the colored track)"
        editor.set_text("run x")
        assert at("ru").is_empty()

    def test_card_content_of_a_variable_is_its_value(self, editor):
        editor.set_text('{"h": "{{ header.height }}"}')
        editor.values.set_source(lambda name: 44 if name == "header.height" else {"height": 44}, lambda text: "44")

        found = editor.hover.card_content_at(self._position(editor, '{"h": "{{ header.he')).help
        assert (found.name, found.summary) == ("header.height", "`44`")
        assert editor.hover.card_content_at(self._position(editor, '{"h": "{{ hea')).help.summary == "`{height}`"

    def test_values_are_shown_after_the_line_when_asked_for(self, editor):
        editor.resize(600, 200)
        editor.show()
        editor.set_text('{"h": "{{ header.height }}"}\n{"x": 1}')
        calls = []
        editor.values.set_source(lambda name: 44, lambda text: calls.append(text) or "44")

        # on: the templates of the visible lines, once (until the values are refreshed)
        editor.values.set_show(True)
        editor.grab()
        editor.grab()
        assert calls == ["{{ header.height }}"]
        editor.values.refresh()
        editor.grab()
        assert calls == ["{{ header.height }}"] * 2

    def test_card_shows_issues_with_the_explanation(self, editor):
        editor.set_text('{"w": "33%"}')
        editor.set_app_markers([SourceIssue(1, 1, 3, Severity.ERROR, "Broken")])
        content = editor.hover.card_content_at(self._position(editor, '{"'))
        assert content.issues == [(Severity.ERROR, "Broken")] and content.help.name == "w"
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        assert "Broken" in editor.hover.card._issues.text()


class TestColorSwatches(TestBase):
    def test_colors_of_a_line_are_its_color_strings_and_templates_rendering_to_colors(self, editor):
        editor.set_text('{"bg_color": "#FF0000", "text_color": "{{ c }}"}\n{"x": 1}')
        editor.values.set_source(lambda name: None, lambda text: "#00FF00")

        assert [color.hex() for color in editor.values.colors_of(editor.document().findBlockByNumber(0).text())] == [
            "#FF0000",
            "#00FF00",
        ]
        assert editor.values.colors_of(editor.document().findBlockByNumber(1).text()) == []

    def test_swatches_are_painted_in_the_gutter(self, editor):
        editor.resize(600, 200)
        editor.show()
        editor.set_text('{"bg_color": "#FF0000"}')

        image = editor.gutter.grab().toImage()

        assert any(
            image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 60
            for x in range(image.width())
            for y in range(20)
        )


class TestFlash(TestBase):
    def test_lines_are_highlighted_for_a_moment(self, editor):
        # GIVEN
        editor.set_text('{\n  "page": 1,\n  "id": 2\n}\n')

        # WHEN
        editor.flash_lines(1, 4, duration_ms=50)

        # THEN
        assert editor.flashed_lines == (1, 4)
        assert sum(s.format.background().color().alpha() > 0 for s in editor.extraSelections()) >= 4
        # a slow machine (CI) may need longer than the duration
        wait_until(lambda: editor.flashed_lines is None)

    def test_typing_clicking_or_a_reload_end_the_highlight(self, editor):
        # GIVEN
        editor.set_text('{"page": 1}\n')

        # WHEN / THEN
        editor.flash_lines(1, 1)
        _type(editor, "x")
        assert editor.flashed_lines is None

        editor.flash_lines(1, 1)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        assert editor.flashed_lines is None

        editor.flash_lines(1, 1)
        editor.set_text('{"page": 2}\n')
        assert editor.flashed_lines is None


class TestColorPicker(TestBase):
    def _editor(self, language=Language.JSONL, text='{"c": "#0D0F14", "d": 1}'):
        editor = CodeEditor(language)
        editor.resize(500, 300)
        editor.show()
        editor.set_text(text)
        return editor

    def _color(self, editor, prefix='{"c": "#0D'):
        position = QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 2, 5)
        return editor._colors.color_at(position)

    def test_finds_the_color_under_the_mouse(self, qapp, settings):
        editor = self._editor()
        number, token = self._color(editor)
        assert (number, token.start, token.end) == (0, 6, 15)
        assert self._color(editor, '{"c"') is None
        editor.close()

    def test_ctrl_click_opens_the_picker_and_edits_the_text(self, qapp, settings):
        # GIVEN
        editor = self._editor()
        edits = []
        editor.textEdited.connect(lambda: edits.append(1))
        position = QPoint(editor.fontMetrics().horizontalAdvance('{"c": "#0D') + 2, 5)

        # WHEN
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)
        assert editor._picker.isVisible()
        editor._picker.set_color(255, 0, 0, 255)
        editor._picker.set_color(0, 128, 255, 255)

        # THEN: the quotes and the case stay, the rest of the line is untouched
        assert editor.toPlainText() == '{"c": "#0080FF", "d": 1}'
        assert edits

        # WHEN: closed, the changes are one step to undo
        editor._picker.close_picker()
        editor.undo()
        assert editor.toPlainText() == '{"c": "#0D0F14", "d": 1}'
        editor.close()

    def test_the_style_of_the_color_is_kept(self, qapp, settings):
        editor = self._editor(Language.YAML, "color: '#0d0f14'")
        editor.edit_color(*self._color_at_start(editor))
        editor._picker.set_color(1, 2, 255, 255)
        assert editor.toPlainText() == "color: '#0102ff'"

        # an alpha other than 255 makes it #AARRGGBB
        editor._picker.set_color(1, 2, 255, 128)
        assert editor.toPlainText() == "color: '#800102ff'"
        editor._picker.set_color(1, 2, 255, 255)
        assert editor.toPlainText() == "color: '#0102ff'"
        editor.close()

    def _color_at_start(self, editor):
        return editor._colors.color_at(QPoint(editor.fontMetrics().horizontalAdvance("color: '#0") + 2, 5))

    def test_the_text_of_the_picker_follows_typing(self, qapp, settings):
        editor = self._editor()
        editor.edit_color(*self._color(editor))
        picker = editor._picker
        picker._text.textEdited.emit("#336699")
        assert editor.toPlainText() == '{"c": "#336699", "d": 1}'
        assert [picker._channels[name].value() for name in "ARGB"] == [255, 51, 102, 153]

        # not a color yet: nothing changes
        picker._text.textEdited.emit("#33")
        assert editor.toPlainText() == '{"c": "#336699", "d": 1}'
        editor.close()

    def test_the_wheel_changes_the_color(self, qapp, settings):
        editor = self._editor(text='{"c": "#FF0000"}')
        editor.edit_color(*self._color(editor, '{"c": "#F'))
        wheel = editor._picker._wheel
        assert wheel.hue == 0 and wheel.saturation == 1.0 and wheel.value == 1.0

        wheel.hue = 120
        wheel.changed.emit()
        assert editor.toPlainText() == '{"c": "#00FF00"}'
        editor.close()

    def test_escape_closes_the_picker(self, qapp, settings):
        editor = self._editor()
        editor.edit_color(*self._color(editor))
        QTest.keyClick(editor._picker, Qt.Key.Key_Escape)
        assert not editor._picker.isVisible()
        assert editor._colors._edit is None
        editor.close()


class TestDirectives(TestBase):
    def _colors(self, editor, line: int):
        """:return: (text, color) of the highlighted ranges of a line"""
        block = editor.document().findBlockByNumber(line - 1)
        return [
            (block.text()[fmt.start : fmt.start + fmt.length], fmt.format.foreground().color().name())
            for fmt in block.layout().formats()
        ]

    def test_the_keys_of_a_directive_have_their_own_color(self, editor):
        from openhasp_config_manager.gui.domain.source.syntax import TokenKind
        from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color

        # WHEN
        editor.set_text('{\n  "!include": "a.jsonl",\n  "vars": {"vars": 1}\n}\n{"vars": 1}')

        # THEN
        directive, key = syntax_color(TokenKind.DIRECTIVE).name(), syntax_color(TokenKind.KEY).name()
        assert ('"!include"', directive) in self._colors(editor, 2)
        # the key of the directive, and a variable named like it
        assert self._colors(editor, 3)[0] == ('"vars"', directive)
        assert ('"vars"', key) in self._colors(editor, 3)
        assert ('"vars"', key) in self._colors(editor, 5)

        # WHEN: the directive goes away, the lines after it are colored again
        cursor = editor.textCursor()
        cursor.setPosition(editor.document().findBlockByNumber(1).position() + 3)
        cursor.insertText("x")

        # THEN
        assert self._colors(editor, 3)[0] == ('"vars"', key)

    def test_the_path_of_an_include_is_completed(self, editor):
        # GIVEN
        editor.completion.set_include_paths(lambda: ["common/parts/tile.jsonl", "common/page.jsonl"])

        # WHEN
        _type(editor, '{"!include": "common/pa')

        # THEN
        assert editor.completion.completer.popup().isVisible()
        assert editor.completion.completer.model().stringList() == ["common/page.jsonl", "common/parts/tile.jsonl"]
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Down)
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText().startswith('{"!include": "common/parts/tile.jsonl"')

    def test_a_directive_offers_its_keys_with_their_explanation(self, editor):
        # GIVEN
        editor.resize(900, 400)
        editor.set_text('{"!include": "a.jsonl", "')
        editor.go_to(1, 25)

        # WHEN
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)

        # THEN
        assert editor.completion.completer.model().stringList() == ["for", "vars"]
        assert editor.completion.card._kind.text() == "Key of an `!include`"

    def test_ctrl_click_on_the_path_of_an_include(self, editor):
        # GIVEN
        editor.set_text('{"!include": "common/parts/tile.jsonl"}')
        paths = []
        editor.includeRequested.connect(paths.append)
        position = QPoint(editor.fontMetrics().horizontalAdvance('{"!include": "common/pa') + 2, 5)

        # WHEN
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)

        # THEN
        assert paths == ["common/parts/tile.jsonl"]
