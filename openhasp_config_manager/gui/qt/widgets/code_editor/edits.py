from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from openhasp_config_manager.gui.domain.source.edit import INDENT, indent_for_new_line, toggle_comment
from openhasp_config_manager.gui.domain.source.format import format_text
from openhasp_config_manager.gui.domain.source.rename import id_at_line, rename_object_id

PAIRS = {"{": "}", "[": "]", '"': '"'}


class EditorEdits(QObject):
    """The edits of a text editor that are more than typing a character: brackets and quotes, lines, format, rename."""

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor

    def text_around_cursor(self) -> Tuple[str, str]:
        """:return: the text of the line before the cursor and after it"""
        cursor = self._editor.textCursor()
        text = cursor.block().text()
        column = cursor.positionInBlock()
        return text[:column], text[column:]

    # --- brackets and quotes ---

    def new_line(self):
        editor = self._editor
        before, after = self.text_around_cursor()
        indent = indent_for_new_line(before, editor.language)
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        stripped = before.rstrip()
        if stripped.endswith(("{", "[")) and after.lstrip().startswith(PAIRS[stripped[-1]]):
            base = indent[: -len(INDENT)] if indent.endswith(INDENT) else indent
            cursor.insertText("\n" + indent + "\n" + base)
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
        else:
            cursor.insertText("\n" + indent)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

    def type_over(self, char: str) -> bool:
        """Typing a closing bracket or quote in front of the same one moves behind it."""
        cursor = self._editor.textCursor()
        text = cursor.block().text()
        column = cursor.positionInBlock()
        if cursor.hasSelection() or column >= len(text) or text[column] != char:
            return False
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        self._editor.setTextCursor(cursor)
        return True

    def type_pair(self, char: str) -> bool:
        """Typing an opening bracket or quote writes the closing one too, unless a word follows."""
        cursor = self._editor.textCursor()
        before, after = self.text_around_cursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(char + selected + PAIRS[char])
            return True
        if after[:1].isalnum() or (char == '"' and (before[-1:].isalnum() or before[-1:] == "\\")):
            return False
        cursor.insertText(char + PAIRS[char])
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
        self._editor.setTextCursor(cursor)
        return True

    def delete_pair(self) -> bool:
        before, after = self.text_around_cursor()
        cursor = self._editor.textCursor()
        if cursor.hasSelection() or not before or not after or PAIRS.get(before[-1]) != after[0]:
            return False
        cursor.beginEditBlock()
        cursor.deletePreviousChar()
        cursor.deleteChar()
        cursor.endEditBlock()
        return True

    # --- lines ---

    def _selected_blocks(self) -> Tuple[int, int]:
        """:return: the first and last block number of the selection (of the cursor line if there is none)"""
        cursor = self._editor.textCursor()
        document = self._editor.document()
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
        if last > first and cursor.selectionEnd() == document.findBlockByNumber(last).position():
            last -= 1  # the selection ends at the start of a line: that line is not part of it
        return first, last

    def _replace_blocks(self, first: int, last: int, lines: List[str]):
        document = self._editor.document()
        start = document.findBlockByNumber(first)
        end = document.findBlockByNumber(last)
        cursor = QTextCursor(start)
        cursor.setPosition(end.position() + end.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("\n".join(lines))
        selection = QTextCursor(document.findBlockByNumber(first))
        selection.setPosition(
            document.findBlockByNumber(first + len(lines) - 1).position()
            + document.findBlockByNumber(first + len(lines) - 1).length()
            - 1,
            QTextCursor.MoveMode.KeepAnchor,
        )
        self._editor.setTextCursor(selection)

    def _block_lines(self, first: int, last: int) -> List[str]:
        return [self._editor.document().findBlockByNumber(n).text() for n in range(first, last + 1)]

    def toggle_comment(self):
        first, last = self._selected_blocks()
        lines = self._block_lines(first, last)
        new_lines = toggle_comment(lines, self._editor.language)
        if new_lines != lines:
            cursor = self._editor.textCursor()
            cursor.beginEditBlock()
            self._replace_blocks(first, last, new_lines)
            cursor.endEditBlock()

    def duplicate_lines(self):
        first, last = self._selected_blocks()
        lines = self._block_lines(first, last)
        end = self._editor.document().findBlockByNumber(last)
        cursor = QTextCursor(end)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText("\n" + "\n".join(lines))
        self._editor.setTextCursor(cursor)

    def indent(self, forward: bool):
        cursor = self._editor.textCursor()
        first, last = self._selected_blocks()
        if forward and first == last and not cursor.hasSelection():
            column = cursor.positionInBlock()
            cursor.insertText(" " * (len(INDENT) - column % len(INDENT)))
            return
        lines = self._block_lines(first, last)
        if forward:
            new_lines = [INDENT + line if line.strip() else line for line in lines]
        else:
            new_lines = [line[min(len(INDENT), len(line) - len(line.lstrip(" "))) :] for line in lines]
        cursor.beginEditBlock()
        self._replace_blocks(first, last, new_lines)
        cursor.endEditBlock()

    # --- format, rename ---

    def format_document(self) -> bool:
        """Indent the lines by their depth and clean the line ends. :return: whether the text changed."""
        formatted = format_text(self._editor.toPlainText(), self._editor.language)
        if formatted == self._editor.toPlainText():
            return False
        self.replace_text(formatted)
        return True

    @property
    def object_id(self) -> Optional[int]:
        """:return: the id of the object at the cursor, None if there is none or it is not a plain number"""
        return id_at_line(self._editor.toPlainText(), self._editor.textCursor().blockNumber() + 1)

    def rename_id(self, new_id: int) -> Optional[str]:
        """
        Change the id of the object at the cursor, and the `parentid` of its children.
        :return: why that is not possible, None if it was done
        """
        try:
            renamed = rename_object_id(self._editor.toPlainText(), self._editor.textCursor().blockNumber() + 1, new_id)
        except ValueError as ex:
            return str(ex)
        if renamed.text != self._editor.toPlainText():
            self.replace_text(renamed.text)
        return None

    def replace_text(self, text: str):
        """Replace the text as one edit that can be undone; the cursor and the view stay where they were."""
        editor = self._editor
        cursor = editor.textCursor()
        line, column = cursor.blockNumber(), cursor.positionInBlock()
        scroll = editor.verticalScrollBar().value()
        editor.folding.unfold_all()
        edit = QTextCursor(editor.document())
        edit.beginEditBlock()
        edit.select(QTextCursor.SelectionType.Document)
        edit.insertText(text)
        edit.endEditBlock()
        block = editor.document().findBlockByNumber(min(line, editor.document().blockCount() - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(column, max(block.length() - 1, 0)))
        editor.setTextCursor(cursor)
        editor.verticalScrollBar().setValue(scroll)
