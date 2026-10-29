import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QTextCursor  # noqa: E402

from openhasp_config_manager.gui.domain.source.syntax import TokenKind  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color  # noqa: E402
from tests import TestBase  # noqa: E402

DIRECTIVE_OBJECT = '{\n  "vars": {"id": 1},\n  "for": {"i": [1]},\n  "!include": "a.jsonl"\n}\n'


def _color_at(editor, line: int, column: int):
    """:return: the text color the highlighter gave a character (lines from 0)"""
    for fmt in editor.document().findBlockByNumber(line).layout().formats():
        if fmt.start <= column < fmt.start + fmt.length:
            return fmt.format.foreground().color()
    return None


def _is_directive(editor, line: int, column: int) -> bool:
    return _color_at(editor, line, column) == syntax_color(TokenKind.DIRECTIVE)


class TestDirectiveKeys(TestBase):
    def test_vars_and_for_before_the_include_of_a_one_line_object(self, editor):
        editor.set_text('{"vars": {"id": 1}, "for": {"i": [1]}, "!include": "a.jsonl"}\n{"vars": 1}\n')

        assert _is_directive(editor, 0, 1)
        assert _is_directive(editor, 0, 21)
        assert not _is_directive(editor, 0, 10)
        assert not _is_directive(editor, 1, 1)

    def test_vars_and_for_before_the_include_of_a_multi_line_object(self, editor):
        editor.set_text(DIRECTIVE_OBJECT + '{\n  "vars": 1\n}\n')

        assert _is_directive(editor, 1, 2)
        assert _is_directive(editor, 2, 2)
        assert _is_directive(editor, 3, 2)
        assert not _is_directive(editor, 1, 11)
        assert not _is_directive(editor, 6, 2)

    def test_adding_or_removing_the_include_below_changes_the_keys_above(self, editor):
        # GIVEN
        editor.set_text('{\n  "vars": {"id": 1},\n  "page": 1\n}\n')
        assert not _is_directive(editor, 1, 2)
        line = editor.document().findBlockByNumber(2)
        cursor = QTextCursor(line)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)

        # WHEN
        cursor.insertText('  "!include": "a.jsonl"')

        # THEN
        assert _is_directive(editor, 1, 2)

        # WHEN
        editor.undo()

        # THEN
        assert not _is_directive(editor, 1, 2)

    def test_a_new_theme_keeps_the_directive_keys(self, editor):
        # GIVEN
        editor.set_text('{\n  "vars": {"id": 1},\n  "page": 1\n}\n')
        editor.refresh_theme()

        # WHEN
        cursor = QTextCursor(editor.document().findBlockByNumber(2))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText('  "!include": "a.jsonl"')

        # THEN: the highlighter of the old theme is gone
        assert _is_directive(editor, 1, 2)
