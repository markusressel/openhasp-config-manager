from typing import List, Optional

from PyQt6.QtCore import QObject, QRegularExpression
from PyQt6.QtGui import QColor, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit

from openhasp_config_manager.gui.qt.theme import current_colors

_MAX_SEARCH_MATCHES = 1000


class EditorSearch(QObject):
    """Search and replace in a text editor: the matches are marked, the editor shows the marks as part of its selections."""

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._expression: Optional[QRegularExpression] = None
        self._flags = QTextDocument.FindFlag(0)

    def set_search(self, text: str, case_sensitive: bool = False, whole_word: bool = False, regex: bool = False) -> bool:
        """
        Mark all matches of a text. An empty text clears the marks.
        :return: whether the search is valid (a regular expression can be broken)
        """
        if not text:
            self._expression = None
            self._editor.update_selections()
            return True
        pattern = text if regex else QRegularExpression.escape(text)
        if whole_word:
            pattern = rf"\b(?:{pattern})\b"
        expression = QRegularExpression(
            pattern,
            QRegularExpression.PatternOption.NoPatternOption
            if case_sensitive
            else QRegularExpression.PatternOption.CaseInsensitiveOption,
        )
        if not expression.isValid():
            self._expression = None
            self._editor.update_selections()
            return False
        self._expression = expression
        self._flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
        self._editor.update_selections()
        return True

    def selections(self) -> List[QTextEdit.ExtraSelection]:
        if self._expression is None:
            return []
        document = self._editor.document()
        result = []
        color = QColor(current_colors().warning)
        color.setAlpha(90)
        cursor = QTextCursor(document)
        while len(result) < _MAX_SEARCH_MATCHES:
            cursor = document.find(self._expression, cursor, self._flags)
            if cursor.isNull():
                break
            if cursor.hasSelection():
                selection = QTextEdit.ExtraSelection()
                selection.format.setBackground(color)
                selection.cursor = QTextCursor(cursor)
                result.append(selection)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        return result

    def find_next(self, forward: bool = True) -> bool:
        """Select the next (or previous) match after the cursor, wrapping around. :return: whether there is one"""
        if self._expression is None:
            return False
        document = self._editor.document()
        flags = self._flags if forward else self._flags | QTextDocument.FindFlag.FindBackward
        cursor = document.find(self._expression, self._editor.textCursor(), flags)
        if cursor.isNull():
            start = QTextCursor(document)
            if not forward:
                start.movePosition(QTextCursor.MoveOperation.End)
            cursor = document.find(self._expression, start, flags)
        if cursor.isNull():
            return False
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        return True

    def replace_current(self, replacement: str) -> bool:
        """Replace the selected match (if the selection is one), then select the next. :return: whether it replaced"""
        cursor = self._editor.textCursor()
        match = (
            self._expression.match(cursor.selectedText()) if self._expression is not None and cursor.hasSelection() else None
        )
        if match is None or not match.hasMatch() or match.capturedLength() != len(cursor.selectedText()):
            self.find_next()
            return False
        cursor.insertText(self._expand(replacement, match))
        self.find_next()
        return True

    def replace_all(self, replacement: str) -> int:
        """:return: how many matches were replaced"""
        if self._expression is None:
            return 0
        document = self._editor.document()
        count = 0
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        found = document.find(self._expression, 0, self._flags)
        while not found.isNull() and count < 100000:
            if found.hasSelection():
                match = self._expression.match(found.selectedText())
                found.insertText(self._expand(replacement, match))
                count += 1
            found = document.find(self._expression, found, self._flags)
        cursor.endEditBlock()
        return count

    @staticmethod
    def _expand(replacement: str, match) -> str:
        """The replacement with `\\1`..`\\9` replaced by the groups of the match."""
        result = replacement
        for group in range(min(match.lastCapturedIndex(), 9), 0, -1):
            result = result.replace(f"\\{group}", match.captured(group))
        return result
