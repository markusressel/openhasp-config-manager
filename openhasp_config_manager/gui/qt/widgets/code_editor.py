from dataclasses import dataclass
from typing import Callable, List, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QRect, QRegularExpression, QSettings, QSize, QStringListModel, Qt
from PyQt6.QtGui import (
    QColor,
    QFontDatabase,
    QKeyEvent,
    QPainter,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextOption,
)
from PyQt6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QToolTip, QWidget

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source_completion import OBJECT_PROPERTIES, complete, completion_context
from openhasp_config_manager.gui.domain.source_edit import INDENT, indent_for_new_line, matching_bracket, toggle_comment
from openhasp_config_manager.gui.domain.source_issues import find_source_issues
from openhasp_config_manager.gui.domain.source_syntax import Language
from openhasp_config_manager.gui.qt.source_highlighter import SourceHighlighter
from openhasp_config_manager.gui.qt.theme import current_colors

_FONT_SIZE_KEY = "editor/font_size"
_DEFAULT_FONT_SIZE = 10
_ISSUE_DELAY_MS = 300
_MAX_SEARCH_MATCHES = 1000
_PAIRS = {"{": "}", "[": "]", '"': '"'}


@dataclass(frozen=True)
class Marker:
    """Something to point out in the text: shown in the gutter, underlined, and explained on hover."""

    line: int  # starts at 1
    column: int
    length: int
    severity: Severity
    message: str


def _marker_color(severity: Severity) -> QColor:
    colors = current_colors()
    return QColor(colors.error if severity == Severity.ERROR else colors.warning)


class _Gutter(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    """
    A text editor for the files of a config directory: syntax colors, line numbers, issue markers, matching brackets,
    smart indentation, comments, completion and search. The logic behind these is in `gui/domain/source_*.py`.
    """

    # the text was changed by the user (not by `set_text`)
    textEdited = QtCore.pyqtSignal()
    # Ctrl+S
    saveRequested = QtCore.pyqtSignal()
    # Ctrl+F
    findRequested = QtCore.pyqtSignal()
    # the problems of the text itself changed
    issuesChanged = QtCore.pyqtSignal()

    def __init__(self, language: Language, parent=None):
        super().__init__(parent)
        self.language = language
        self._loading = False
        self._text_markers: List[Marker] = []
        self._app_markers: List[Marker] = []
        self._search: Optional[QRegularExpression] = None
        self._search_flags = QTextDocument.FindFlag(0)
        self._variables: Callable[[], List[str]] = lambda: []
        self._completion_start = 0

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))
        self.setMouseTracking(True)
        self._set_font_size(QSettings().value(_FONT_SIZE_KEY, _DEFAULT_FONT_SIZE, type=int))

        self.highlighter = SourceHighlighter(self.document(), language)
        self._gutter = _Gutter(self)

        self._completer = QCompleter(QStringListModel(self), self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.activated.connect(self._insert_completion)

        self._issue_timer = QtCore.QTimer(self)
        self._issue_timer.setSingleShot(True)
        self._issue_timer.setInterval(_ISSUE_DELAY_MS)
        self._issue_timer.timeout.connect(self.update_issues)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._update_selections)
        self.textChanged.connect(self._on_text_changed)
        self._update_gutter_width()
        self._update_selections()

    # --- text ---

    def set_text(self, text: str):
        """Replace the text without it counting as an edit of the user. Cursor and scroll position stay where they were."""
        if text == self.toPlainText():
            return
        cursor = self.textCursor()
        line, column = cursor.blockNumber(), cursor.positionInBlock()
        scroll = self.verticalScrollBar().value()
        self._loading = True
        try:
            self.setPlainText(text)
        finally:
            self._loading = False
        block = self.document().findBlockByNumber(min(line, self.document().blockCount() - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(column, block.length() - 1))
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(scroll)
        self.update_issues()

    def go_to(self, line: int, column: int = 0):
        """Put the cursor at a line (starts at 1) and scroll so it is in the middle of the view."""
        block = self.document().findBlockByNumber(max(line - 1, 0))
        if not block.isValid():
            block = self.document().lastBlock()
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(column, max(block.length() - 1, 0)))
        self.setTextCursor(cursor)
        self.centerCursor()
        if self.cursorRect().right() < self.viewport().width() // 2:
            # centering also scrolls sideways: a line that starts at the left shows from its start
            self.horizontalScrollBar().setValue(0)
        self.setFocus()

    @property
    def cursor_line_column(self) -> tuple:
        """:return: (line, column) of the cursor, both starting at 1"""
        cursor = self.textCursor()
        return cursor.blockNumber() + 1, cursor.positionInBlock() + 1

    def _on_text_changed(self):
        if self._loading:
            return
        self._issue_timer.start()
        self._update_selections()
        self.textEdited.emit()

    # --- issues and markers ---

    @property
    def issues(self) -> List[Marker]:
        return list(self._text_markers)

    def update_issues(self):
        """Look at the text for problems now (otherwise a moment after the last edit)."""
        self._issue_timer.stop()
        self._text_markers = [
            Marker(issue.line, issue.column, issue.length, issue.severity, issue.message)
            for issue in find_source_issues(self.toPlainText(), self.language)
        ]
        self._update_selections()
        self._gutter.update()
        self.issuesChanged.emit()

    def set_app_markers(self, markers: List[Marker]):
        """Problems found by the app for the objects of this file (e.g. one is outside of the screen)."""
        self._app_markers = list(markers)
        self._update_selections()
        self._gutter.update()

    def _markers(self) -> List[Marker]:
        return self._text_markers + self._app_markers

    def _markers_at(self, line: int) -> List[Marker]:
        return [marker for marker in self._markers() if marker.line == line]

    # --- appearance ---

    def _set_font_size(self, size: int):
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setFamilies(["Roboto Mono", font.family()])
        font.setPointSize(size)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))

    def zoom(self, delta: int):
        size = max(6, min(32, self.font().pointSize() + delta))
        self._set_font_size(size)
        QSettings().setValue(_FONT_SIZE_KEY, size)
        self._update_gutter_width()

    def reset_zoom(self):
        self.zoom(_DEFAULT_FONT_SIZE - self.font().pointSize())

    def set_word_wrap(self, wrap: bool):
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else QPlainTextEdit.LineWrapMode.NoWrap)

    def set_show_whitespace(self, show: bool):
        option = self.document().defaultTextOption()
        flags = option.flags()
        option.setFlags(flags | QTextOption.Flag.ShowTabsAndSpaces if show else flags & ~QTextOption.Flag.ShowTabsAndSpaces)
        self.document().setDefaultTextOption(option)

    def refresh_theme(self):
        self.highlighter.setDocument(None)
        self.highlighter = SourceHighlighter(self.document(), self.language)
        self._update_selections()
        self._gutter.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    # --- gutter ---

    def gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 20 + self.fontMetrics().horizontalAdvance("9") * max(digits, 2)

    def _update_gutter_width(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self._gutter.setGeometry(QRect(area.left(), area.top(), self.gutter_width(), area.height()))

    def paint_gutter(self, event):
        painter = QPainter(self._gutter)
        palette = self.palette()
        painter.fillRect(event.rect(), palette.color(QPalette.ColorRole.AlternateBase))
        current = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            if block.isVisible() and bottom >= event.rect().top():
                markers = self._markers_at(number + 1)
                if markers:
                    worst = Severity.ERROR if any(m.severity == Severity.ERROR for m in markers) else Severity.WARNING
                    painter.setBrush(_marker_color(worst))
                    painter.setPen(Qt.PenStyle.NoPen)
                    size = height // 2
                    painter.drawEllipse(4, top + (height - size) // 2, size, size)
                font = painter.font()
                font.setBold(number == current)
                painter.setFont(font)
                painter.setPen(
                    palette.color(QPalette.ColorRole.WindowText if number == current else QPalette.ColorRole.PlaceholderText)
                )
                painter.drawText(0, top, self._gutter.width() - 6, height, Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            number += 1

    # --- selections: current line, brackets, issues, search ---

    def _update_selections(self):
        selections: List[QTextEdit.ExtraSelection] = []

        line = QTextEdit.ExtraSelection()
        color = self.palette().color(QPalette.ColorRole.Highlight)
        color.setAlpha(28)
        line.format.setBackground(color)
        line.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        line.cursor = self.textCursor()
        line.cursor.clearSelection()
        selections.append(line)

        selections += self._bracket_selections()
        selections += self._marker_selections()
        selections += self._search_selections()
        self.setExtraSelections(selections)

    def _bracket_selections(self) -> List[QTextEdit.ExtraSelection]:
        text = self.toPlainText()
        position = self.textCursor().position()
        for candidate in (position, position - 1):
            if 0 <= candidate < len(text) and text[candidate] in "{}[]":
                partner = matching_bracket(text, candidate, self.language)
                if partner is None:
                    return []
                result = []
                for index in (candidate, partner):
                    selection = QTextEdit.ExtraSelection()
                    selection.format.setBackground(self.palette().color(QPalette.ColorRole.Highlight).lighter(130))
                    selection.format.setForeground(self.palette().color(QPalette.ColorRole.HighlightedText))
                    selection.cursor = QTextCursor(self.document())
                    selection.cursor.setPosition(index)
                    selection.cursor.setPosition(index + 1, QTextCursor.MoveMode.KeepAnchor)
                    result.append(selection)
                return result
        return []

    def _marker_selections(self) -> List[QTextEdit.ExtraSelection]:
        result = []
        for marker in self._markers():
            block = self.document().findBlockByNumber(marker.line - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selection.format.setUnderlineColor(_marker_color(marker.severity))
            start = block.position() + min(marker.column, max(block.length() - 1, 0))
            selection.cursor = QTextCursor(self.document())
            selection.cursor.setPosition(start)
            if marker.length > 1:
                selection.cursor.setPosition(
                    min(start + marker.length, block.position() + block.length() - 1), QTextCursor.MoveMode.KeepAnchor
                )
            else:
                # a position, not a range: the rest of the word, or the character
                selection.cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            result.append(selection)
        return result

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            markers = self._markers_at(cursor.blockNumber() + 1)
            if markers:
                QToolTip.showText(event.globalPos(), "\n".join(marker.message for marker in markers), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    # --- search ---

    def set_search(self, text: str, case_sensitive: bool = False, whole_word: bool = False, regex: bool = False) -> bool:
        """
        Mark all matches of a text. An empty text clears the marks.
        :return: whether the search is valid (a regular expression can be broken)
        """
        if not text:
            self._search = None
            self._update_selections()
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
            self._search = None
            self._update_selections()
            return False
        self._search = expression
        self._search_flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
        self._update_selections()
        return True

    def _search_selections(self) -> List[QTextEdit.ExtraSelection]:
        if self._search is None:
            return []
        result = []
        color = QColor(current_colors().warning)
        color.setAlpha(90)
        cursor = QTextCursor(self.document())
        while len(result) < _MAX_SEARCH_MATCHES:
            cursor = self.document().find(self._search, cursor, self._search_flags)
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
        if self._search is None:
            return False
        flags = self._search_flags if forward else self._search_flags | QTextDocument.FindFlag.FindBackward
        cursor = self.document().find(self._search, self.textCursor(), flags)
        if cursor.isNull():
            start = QTextCursor(self.document())
            if not forward:
                start.movePosition(QTextCursor.MoveOperation.End)
            cursor = self.document().find(self._search, start, flags)
        if cursor.isNull():
            return False
        self.setTextCursor(cursor)
        self.centerCursor()
        return True

    def replace_current(self, replacement: str) -> bool:
        """Replace the selected match (if the selection is one), then select the next. :return: whether it replaced"""
        cursor = self.textCursor()
        match = self._search.match(cursor.selectedText()) if self._search is not None and cursor.hasSelection() else None
        if match is None or not match.hasMatch() or match.capturedLength() != len(cursor.selectedText()):
            self.find_next()
            return False
        cursor.insertText(self._expand(replacement, match))
        self.find_next()
        return True

    def replace_all(self, replacement: str) -> int:
        """:return: how many matches were replaced"""
        if self._search is None:
            return 0
        count = 0
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        found = self.document().find(self._search, 0, self._search_flags)
        while not found.isNull() and count < 100000:
            if found.hasSelection():
                match = self._search.match(found.selectedText())
                found.insertText(self._expand(replacement, match))
                count += 1
            found = self.document().find(self._search, found, self._search_flags)
        cursor.endEditBlock()
        return count

    @staticmethod
    def _expand(replacement: str, match) -> str:
        """The replacement with `\\1`..`\\9` replaced by the groups of the match."""
        result = replacement
        for group in range(min(match.lastCapturedIndex(), 9), 0, -1):
            result = result.replace(f"\\{group}", match.captured(group))
        return result

    # --- keys ---

    def keyPressEvent(self, event: QKeyEvent):
        popup = self._completer.popup()
        key = event.key()
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        if popup.isVisible() and key in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Escape,
            Qt.Key.Key_Backtab,
        ):
            event.ignore()
            return
        if control and key == Qt.Key.Key_S:
            self.saveRequested.emit()
        elif control and key == Qt.Key.Key_F:
            self.findRequested.emit()
        elif control and key == Qt.Key.Key_Slash:
            self._toggle_comment()
        elif control and key == Qt.Key.Key_D:
            self._duplicate_lines()
        elif control and key == Qt.Key.Key_Space:
            self._show_completion(force=True)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not control:
            self._new_line()
        elif key == Qt.Key.Key_Tab and not control:
            self._indent(True)
        elif key == Qt.Key.Key_Backtab:
            self._indent(False)
        elif key == Qt.Key.Key_Backspace and not modifiers and self._delete_pair():
            pass
        elif event.text() in _PAIRS.values() and not control and self._type_over(event.text()):
            pass
        elif event.text() in _PAIRS and not control and self._type_pair(event.text()):
            pass
        else:
            super().keyPressEvent(event)
            if event.text() and (event.text().isalnum() or event.text() in '_."{'):
                self._show_completion()
            elif popup.isVisible():
                popup.hide()

    def _block_text_around_cursor(self):
        cursor = self.textCursor()
        text = cursor.block().text()
        column = cursor.positionInBlock()
        return text[:column], text[column:]

    def _new_line(self):
        before, after = self._block_text_around_cursor()
        indent = indent_for_new_line(before, self.language)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        stripped = before.rstrip()
        if stripped.endswith(("{", "[")) and after.lstrip().startswith(_PAIRS[stripped[-1]]):
            base = indent[: -len(INDENT)] if indent.endswith(INDENT) else indent
            cursor.insertText("\n" + indent + "\n" + base)
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
        else:
            cursor.insertText("\n" + indent)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _type_over(self, char: str) -> bool:
        """Typing a closing bracket or quote in front of the same one moves behind it."""
        cursor = self.textCursor()
        text = cursor.block().text()
        column = cursor.positionInBlock()
        if cursor.hasSelection() or column >= len(text) or text[column] != char:
            return False
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        self.setTextCursor(cursor)
        return True

    def _type_pair(self, char: str) -> bool:
        """Typing an opening bracket or quote writes the closing one too, unless a word follows."""
        cursor = self.textCursor()
        before, after = self._block_text_around_cursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(char + selected + _PAIRS[char])
            return True
        if after[:1].isalnum() or (char == '"' and (before[-1:].isalnum() or before[-1:] == "\\")):
            return False
        cursor.insertText(char + _PAIRS[char])
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
        self.setTextCursor(cursor)
        return True

    def _delete_pair(self) -> bool:
        before, after = self._block_text_around_cursor()
        cursor = self.textCursor()
        if cursor.hasSelection() or not before or not after or _PAIRS.get(before[-1]) != after[0]:
            return False
        cursor.beginEditBlock()
        cursor.deletePreviousChar()
        cursor.deleteChar()
        cursor.endEditBlock()
        return True

    def _selected_blocks(self) -> tuple:
        """:return: the first and last block number of the selection (of the cursor line if there is none)"""
        cursor = self.textCursor()
        first = self.document().findBlock(cursor.selectionStart()).blockNumber()
        last = self.document().findBlock(cursor.selectionEnd()).blockNumber()
        if last > first and cursor.selectionEnd() == self.document().findBlockByNumber(last).position():
            last -= 1  # the selection ends at the start of a line: that line is not part of it
        return first, last

    def _replace_blocks(self, first: int, last: int, lines: List[str]):
        document = self.document()
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
        self.setTextCursor(selection)

    def _block_lines(self, first: int, last: int) -> List[str]:
        return [self.document().findBlockByNumber(n).text() for n in range(first, last + 1)]

    def _toggle_comment(self):
        first, last = self._selected_blocks()
        lines = self._block_lines(first, last)
        new_lines = toggle_comment(lines, self.language)
        if new_lines != lines:
            cursor = self.textCursor()
            cursor.beginEditBlock()
            self._replace_blocks(first, last, new_lines)
            cursor.endEditBlock()

    def _duplicate_lines(self):
        first, last = self._selected_blocks()
        lines = self._block_lines(first, last)
        end = self.document().findBlockByNumber(last)
        cursor = QTextCursor(end)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText("\n" + "\n".join(lines))
        self.setTextCursor(cursor)

    def _indent(self, forward: bool):
        cursor = self.textCursor()
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

    # --- completion ---

    def set_variables(self, variables: Callable[[], List[str]]):
        """The names of the template variables that can be used in this file (asked when a template is typed)."""
        self._variables = variables

    def _show_completion(self, force: bool = False):
        before, _ = self._block_text_around_cursor()
        context = completion_context(before, self.language)
        if context is None:
            self._completer.popup().hide()
            return
        words = complete(context, OBJECT_PROPERTIES, self._variables())
        if not words or (not force and not context.prefix):
            self._completer.popup().hide()
            return
        self._completion_start = context.start
        self._completer.model().setStringList(words)
        self._completer.setCompletionPrefix(context.prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 8)
        self._completer.complete(rect)

    def _insert_completion(self, word: str):
        cursor = self.textCursor()
        cursor.setPosition(cursor.block().position() + self._completion_start, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(word)
        self.setTextCursor(cursor)
