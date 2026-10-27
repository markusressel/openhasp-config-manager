from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QPoint
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from openhasp_config_manager.gui.domain.colors import Argb, parse_color
from openhasp_config_manager.gui.domain.source_syntax import Language, Token, TokenKind, tokenize_line
from openhasp_config_manager.gui.qt.widgets.color_picker import ColorPicker


class EditorColors(QObject):
    """Edits the color strings of a text editor with a picker next to them (the picker is a child of the editor)."""

    def __init__(self, editor: QPlainTextEdit, language: Language):
        super().__init__(editor)
        self._editor = editor
        self._language = language
        # the color the picker changes: (block number, start, end of the text with its quotes, whether the first change was made)
        self._edit: Optional[List] = None
        self.picker = ColorPicker(editor)
        self.picker.colorChanged.connect(self._on_picked)
        self.picker.closed.connect(self._end_edit)

    def color_at(self, position: QPoint) -> Optional[Tuple[int, Token]]:
        """:return: (block number, token) of the color string at a position of the viewport"""
        cursor = self._editor.cursorForPosition(position)
        text, column = cursor.block().text(), cursor.positionInBlock()
        for token in tokenize_line(text, self._language):
            if token.kind == TokenKind.COLOR and token.start <= column < token.end:
                return cursor.blockNumber(), token
        return None

    def edit(self, block_number: int, token: Token):
        """Open the color picker for the color string (with its quotes) at a place of the text."""
        editor = self._editor
        block = editor.document().findBlockByNumber(block_number)
        text = token.text(block.text())
        argb = parse_color(text[1:-1])
        if argb is None:
            return
        self._edit = [block_number, token.start, token.end, False]
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + token.start)
        rect = editor.cursorRect(cursor)
        anchor = editor.viewport().mapTo(editor, rect.bottomLeft())
        self.picker.open(argb)
        x = min(max(anchor.x(), 4), max(editor.width() - self.picker.width() - 4, 4))
        y = anchor.y() + 4
        if y + self.picker.height() > editor.height():
            y = max(editor.viewport().mapTo(editor, rect.topLeft()).y() - self.picker.height() - 4, 4)
        self.picker.move(x, y)

    def _on_picked(self, argb: Argb):
        """The picker changed the color: write it into the text, as one step of the undo history."""
        if self._edit is None:
            return
        block_number, start, end, started = self._edit
        document = self._editor.document()
        block = document.findBlockByNumber(block_number)
        quote = block.text()[start]
        cursor = QTextCursor(document)
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        # the changes while the picker is open are one step to undo
        if started:
            cursor.joinPreviousEditBlock()
        else:
            cursor.beginEditBlock()
        new_text = f"{quote}{argb.hex()}{quote}"
        cursor.insertText(new_text)
        cursor.endEditBlock()
        self._edit = [block_number, start, start + len(new_text), True]

    def _end_edit(self):
        self._edit = None
        self._editor.setFocus()
