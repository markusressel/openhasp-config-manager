import re
from typing import Callable, List, Optional, Set, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRegularExpression, QSettings, QSize, QStringListModel, Qt
from PyQt6.QtGui import (
    QAction,
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
from PyQt6.QtWidgets import QCompleter, QMenu, QPlainTextEdit, QTextEdit, QWidget

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source_completion import (
    CompletionContext,
    complete,
    completion_context,
    properties_for,
    property_insertion,
)
from openhasp_config_manager.gui.domain.source_docs import help_at, object_type_at_line, property_help
from openhasp_config_manager.gui.domain.source_edit import INDENT, indent_for_new_line, matching_bracket, toggle_comment
from openhasp_config_manager.gui.domain.source_format import format_text
from openhasp_config_manager.gui.domain.source_issues import SourceIssue, find_source_issues
from openhasp_config_manager.gui.domain.source_links import Link, link_at
from openhasp_config_manager.gui.domain.source_objects import SourceObject, foldable, object_at_line, scan_objects
from openhasp_config_manager.gui.domain.source_rename import id_at_line, rename_object_id
from openhasp_config_manager.gui.domain.source_syntax import Language, Token
from openhasp_config_manager.gui.domain.variable_definitions import Definition, key_at
from openhasp_config_manager.gui.domain.variable_references import part_at
from openhasp_config_manager.gui.qt.source_highlighter import SourceHighlighter
from openhasp_config_manager.gui.qt.widgets.editor_colors import EditorColors
from openhasp_config_manager.gui.qt.widgets.hover_card import CardContent, HoverCard
from openhasp_config_manager.gui.qt.theme import current_colors

_FONT_SIZE_KEY = "editor/font_size"
_DEFAULT_FONT_SIZE = 10
_ISSUE_DELAY_MS = 300
# how long the mouse has to rest on a property before its explanation shows (the default of Qt is about 700 ms)
_HOVER_DELAY_MS = 120
# how long the card stays when the mouse left the property and did not reach the card yet
_HOVER_GRACE_MS = 300
_MAX_SEARCH_MATCHES = 1000
_PAIRS = {"{": "}", "[": "]", '"': '"'}
_FOLD_WIDTH = 14
# how long `flash_lines` highlights lines
FLASH_MS = 3000
# the opacity of the text of lines with a hint, 0..255
_HINT_ALPHA = 110
# the opacity of the background of flashed lines, 0..255
_FLASH_ALPHA = 80
_CODE = re.compile(r"`([^`]+)`")


class _HideWith(QObject):
    """Hides a widget whenever the watched widget is hidden."""

    def __init__(self, watched: QWidget, follower: QWidget):
        super().__init__(watched)
        self._follower = follower
        watched.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Hide:
            self._follower.hide()
        return False


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

    def mousePressEvent(self, event):
        self._editor.gutter_clicked(round(event.position().y()))


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
    # the cursor moved into another object (its index in the file) or out of all objects (-1)
    cursorObjectChanged = QtCore.pyqtSignal(int)
    # Shift+F6, or "Rename id" of the context menu
    renameRequested = QtCore.pyqtSignal()
    # Ctrl+click on a reference to another file: its name on the plate (`pages.jsonl` for `L:/pages.jsonl`)
    linkRequested = QtCore.pyqtSignal(str)
    # Ctrl+click on a part of a variable in a template whose definition is known: the variable up to that part
    definitionRequested = QtCore.pyqtSignal(str)
    # Ctrl+click on the key of a variable in a YAML file: the variable, and where the mouse is (global)
    usagesRequested = QtCore.pyqtSignal(str, QPoint)
    # the "back" and "forward" buttons of the mouse
    backRequested = QtCore.pyqtSignal()
    forwardRequested = QtCore.pyqtSignal()

    def __init__(self, language: Language, parent=None):
        super().__init__(parent)
        self.language = language
        self._loading = False
        self._text_markers: List[SourceIssue] = []
        self._app_markers: List[SourceIssue] = []
        self._hints: List[SourceIssue] = []
        self._search: Optional[QRegularExpression] = None
        self._search_flags = QTextDocument.FindFlag(0)
        self._variables: Callable[[], List[str]] = lambda: []
        self._find_definition: Callable[[str], Optional[Definition]] = lambda name: None
        self._colors = EditorColors(self, language)
        self._picker = self._colors.picker
        # the first lines of the folded objects
        self._folded: Set[int] = set()
        self._objects: List[SourceObject] = []
        self._objects_revision = -1
        self._object_index = -1
        # the reference under the mouse while Ctrl is pressed: (block number, link)
        self._hover_link: Optional[Tuple[int, Link]] = None
        # the lines (first, last, starting at 1) highlighted for a moment, see `flash_lines`
        self._flash: Optional[Tuple[int, int]] = None
        self._flash_timer = QtCore.QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.end_flash)

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * len(INDENT))
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._set_font_size(QSettings().value(_FONT_SIZE_KEY, _DEFAULT_FONT_SIZE, type=int))

        self.highlighter = SourceHighlighter(self.document(), language)
        self._gutter = _Gutter(self)

        self._completer = QCompleter(QStringListModel(self), self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.activated.connect(self._insert_completion)
        # what is completed, for the explanation of the highlighted entry: "property" or "variable", and the `obj` of the object
        self._completion_kind = "property"
        self._completion_context: Optional[CompletionContext] = None
        self._completion_object_type: Optional[str] = None
        self._completion_card = HoverCard(self, interactive=False)
        self._watched_popup: Optional[QWidget] = None
        self._completer.highlighted[str].connect(self._show_completion_docs)

        # shows the explanation under the mouse soon after it came to rest, not only after the (long) delay of Qt
        self._hover_timer = QtCore.QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(_HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._show_hover_card)
        self._hover_position = QPoint()
        # the card of the property under the mouse: it stays while the mouse is on the property or on the card, so its text can be
        # selected and copied
        self._hover_card = HoverCard(self, interactive=True)
        self._hover_card.mouseEntered.connect(lambda: self._hover_grace_timer.stop())
        self._hover_card.mouseLeft.connect(lambda: self._hover_grace_timer.start())
        self._hover_grace_timer = QtCore.QTimer(self)
        self._hover_grace_timer.setSingleShot(True)
        self._hover_grace_timer.setInterval(_HOVER_GRACE_MS)
        self._hover_grace_timer.timeout.connect(self._hide_hover_card)
        # what the card is about, in the coordinates of the viewport: moving inside of it keeps the card
        self._tip_area = QRect()
        self.verticalScrollBar().valueChanged.connect(lambda _value: self._hide_hover_card())

        self._issue_timer = QtCore.QTimer(self)
        self._issue_timer.setSingleShot(True)
        self._issue_timer.setInterval(_ISSUE_DELAY_MS)
        self._issue_timer.timeout.connect(self.update_issues)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.blockCountChanged.connect(lambda _count: self.unfold_all())
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
        # the lines may be others now
        self.end_flash()
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
    def issues(self) -> List[SourceIssue]:
        return list(self._text_markers)

    def update_issues(self):
        """Look at the text for problems now (otherwise a moment after the last edit)."""
        self._issue_timer.stop()
        self._text_markers = find_source_issues(self.toPlainText(), self.language)
        self._update_selections()
        self._gutter.update()
        self.issuesChanged.emit()

    def set_app_markers(self, markers: List[SourceIssue]):
        """Problems found by the app for the objects of this file (e.g. one is outside of the screen)."""
        self._app_markers = list(markers)
        self._update_selections()
        self._gutter.update()

    def set_hints(self, hints: List[SourceIssue]):
        """Things worth knowing about lines, that are no problems (e.g. a variable that is not used): dimmed, explained on hover."""
        self._hints = list(hints)
        self._update_selections()

    def _hints_at(self, line: int) -> List[SourceIssue]:
        return [hint for hint in self._hints if hint.line == line]

    def _markers(self) -> List[SourceIssue]:
        return self._text_markers + self._app_markers

    def _markers_at(self, line: int) -> List[SourceIssue]:
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
        return 20 + _FOLD_WIDTH + self.fontMetrics().horizontalAdvance("9") * max(digits, 2)

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
        fold_starts = {start for start, _ in self.fold_ranges()}
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
                painter.drawText(
                    0, top, self._gutter.width() - 6 - _FOLD_WIDTH, height, Qt.AlignmentFlag.AlignRight, str(number + 1)
                )
                if number + 1 in fold_starts:
                    painter.drawText(
                        self._gutter.width() - _FOLD_WIDTH - 2,
                        top,
                        _FOLD_WIDTH,
                        height,
                        Qt.AlignmentFlag.AlignCenter,
                        "▸" if number + 1 in self._folded else "▾",
                    )
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
        selections += self._hint_selections()
        selections += self._search_selections()
        selections += self._link_selections()
        selections += self._flash_selections()
        self.setExtraSelections(selections)
        self._reveal_cursor()
        self._notify_object()

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

    def _hint_selections(self) -> List[QTextEdit.ExtraSelection]:
        color = self.palette().color(QPalette.ColorRole.Text)
        color.setAlpha(_HINT_ALPHA)
        result = []
        for hint in self._hints:
            block = self.document().findBlockByNumber(hint.line - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.format.setForeground(color)
            selection.format.setFontItalic(True)
            start = block.position() + min(hint.column, max(block.length() - 1, 0))
            selection.cursor = QTextCursor(self.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(
                min(start + hint.length, block.position() + block.length() - 1), QTextCursor.MoveMode.KeepAnchor
            )
            result.append(selection)
        return result

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            # the card of the hover replaces the tool tip, which comes late and goes away when the mouse moves
            return True
        return super().event(event)

    def _card_content_at(self, position: QPoint) -> CardContent:
        """:return: the problems of the line and the explanation of the property, at a position of the viewport"""
        cursor = self.cursorForPosition(position)
        line = cursor.blockNumber() + 1
        issues = [(marker.severity, marker.message) for marker in self._markers_at(line) + self._hints_at(line)]
        found = None
        if self.language == Language.JSONL:
            found = help_at(self.objects(), cursor.block().text(), cursor.blockNumber() + 1, cursor.positionInBlock())
        return CardContent(issues, found)

    def _tip_area_at(self, position: QPoint) -> QRect:
        """:return: the area of the viewport the card at a position is about (a word, or the line for an issue)"""
        cursor = self.cursorForPosition(position)
        line = cursor.blockNumber() + 1
        if (self._markers_at(line) or self._hints_at(line)) and not self._card_content_at(position).help:
            return self.blockBoundingGeometry(cursor.block()).translated(self.contentOffset()).toRect()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        first, last = QTextCursor(cursor), QTextCursor(cursor)
        first.setPosition(cursor.selectionStart())
        last.setPosition(cursor.selectionEnd())
        return self.cursorRect(first).united(self.cursorRect(last))

    def _show_hover_card(self):
        position = self._hover_position
        if not self.viewport().underMouse():
            return
        content = self._card_content_at(position)
        if content.is_empty():
            self._hover_grace_timer.start()
            return
        area = self._tip_area_at(position)
        key = (self.cursorForPosition(position).blockNumber(), area.left(), area.right())
        self._hover_grace_timer.stop()
        if self._hover_card.isVisible() and self._hover_card.key == key:
            return
        self._tip_area = area
        anchor = QRect(self.viewport().mapTo(self, area.topLeft()), area.size())
        self._hover_card.show_content(content, anchor, key)

    def _hide_hover_card(self):
        self._hover_timer.stop()
        self._hover_grace_timer.stop()
        self._tip_area = QRect()
        self._hover_card.hide()

    # --- flash ---

    @property
    def flashed_lines(self) -> Optional[Tuple[int, int]]:
        """:return: the lines (first, last, starting at 1) that are highlighted for a moment, None if none are"""
        return self._flash

    def flash_lines(self, first: int, last: int, duration_ms: int = FLASH_MS):
        """
        Highlight lines (starting at 1) for a moment, e.g. those of the object selected in the preview, so they are easy to find.
        The highlight ends after `duration_ms`, or as soon as the user types or clicks in the editor: it would be in the way.
        """
        self._flash = (first, last)
        self._flash_timer.start(duration_ms)
        self._update_selections()

    def end_flash(self):
        if self._flash is None:
            return
        self._flash = None
        self._flash_timer.stop()
        self._update_selections()

    def _flash_selections(self) -> List[QTextEdit.ExtraSelection]:
        if self._flash is None:
            return []
        first, last = self._flash
        color = self.palette().color(QPalette.ColorRole.Highlight)
        color.setAlpha(_FLASH_ALPHA)
        result = []
        for number in range(first, last + 1):
            block = self.document().findBlockByNumber(number - 1)
            if not block.isValid():
                break
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = QTextCursor(block)
            result.append(selection)
        return result

    def mousePressEvent(self, event):
        self.end_flash()
        self._hide_hover_card()
        if event.button() in (Qt.MouseButton.BackButton, Qt.MouseButton.ForwardButton):
            (self.backRequested if event.button() == Qt.MouseButton.BackButton else self.forwardRequested).emit()
            event.accept()
            return
        super().mousePressEvent(event)

    # --- objects, folding ---

    def objects(self) -> List[SourceObject]:
        """:return: the objects of the text (.jsonl files only)"""
        revision = self.document().revision()
        if revision != self._objects_revision:
            self._objects = scan_objects(self.toPlainText()) if self.language == Language.JSONL else []
            self._objects_revision = revision
        return self._objects

    def object_at_cursor(self) -> Optional[SourceObject]:
        return object_at_line(self.objects(), self.textCursor().blockNumber() + 1)

    def _notify_object(self):
        if self._loading:
            return
        found = self.object_at_cursor()
        index = -1 if found is None else found.index
        if index != self._object_index:
            self._object_index = index
            self.cursorObjectChanged.emit(index)

    def fold_ranges(self) -> List[Tuple[int, int]]:
        """:return: (first line, last line) of the objects that can be folded; the lines in between are hidden when folded"""
        return foldable(self.objects())

    def is_folded(self, line: int) -> bool:
        return line in self._folded

    def fold(self, line: int) -> bool:
        """Hide the lines of the object that starts at a line (starts at 1). :return: whether there is such an object"""
        return self._set_folded(line, True)

    def unfold(self, line: int) -> bool:
        return self._set_folded(line, False)

    def toggle_fold(self, line: int) -> bool:
        return self._set_folded(line, line not in self._folded)

    def fold_at_cursor(self):
        """Fold the object of the cursor."""
        found = self.object_at_cursor()
        if found is not None:
            self.fold(found.start_line)
            if self.textCursor().blockNumber() + 1 > found.start_line:
                self._move_cursor_to_line(found.start_line)

    def unfold_at_cursor(self):
        found = self.object_at_cursor()
        if found is not None:
            self.unfold(found.start_line)

    def fold_all(self):
        for start, _ in self.fold_ranges():
            self.fold(start)
        found = self.object_at_cursor()
        if found is not None:
            self._move_cursor_to_line(found.start_line)

    def unfold_all(self):
        for start in sorted(self._folded):
            self._set_folded(start, False)

    def _set_folded(self, line: int, folded: bool) -> bool:
        end = next((end for start, end in self.fold_ranges() if start == line), None)
        if end is None:
            return False
        if folded:
            self._folded.add(line)
        else:
            self._folded.discard(line)
        # the lines between the brackets: the first and the last stay visible
        for number in range(line + 1, end):
            block = self.document().findBlockByNumber(number - 1)
            if block.isValid():
                block.setVisible(not folded)
        first = self.document().findBlockByNumber(line - 1)
        self.document().markContentsDirty(first.position(), self.document().characterCount() - first.position())
        self.viewport().update()
        self._gutter.update()
        return True

    def _reveal_cursor(self):
        """Unfold what hides the cursor (it was moved into a folded object by a search, a jump to an error, ...)."""
        if not self._folded or self.textCursor().block().isVisible():
            return
        line = self.textCursor().blockNumber() + 1
        for start, end in self.fold_ranges():
            if start in self._folded and start < line < end:
                self.unfold(start)

    def _move_cursor_to_line(self, line: int):
        block = self.document().findBlockByNumber(line - 1)
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(self.textCursor().positionInBlock(), max(block.length() - 1, 0)))
        self.setTextCursor(cursor)

    def gutter_clicked(self, y: int):
        """A click in the gutter folds or unfolds the object that starts in that line."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid():
            bottom = top + round(self.blockBoundingRect(block).height())
            if block.isVisible() and top <= y < bottom:
                self.toggle_fold(block.blockNumber() + 1)
                return
            if top > y:
                return
            block = block.next()
            top = bottom

    # --- format, rename ---

    def format_document(self) -> bool:
        """Indent the lines by their depth and clean the line ends. :return: whether the text changed."""
        formatted = format_text(self.toPlainText(), self.language)
        if formatted == self.toPlainText():
            return False
        self._replace_text(formatted)
        return True

    @property
    def object_id(self) -> Optional[int]:
        """:return: the id of the object at the cursor, None if there is none or it is not a plain number"""
        return id_at_line(self.toPlainText(), self.textCursor().blockNumber() + 1)

    def rename_id(self, new_id: int) -> Optional[str]:
        """
        Change the id of the object at the cursor, and the `parentid` of its children.
        :return: why that is not possible, None if it was done
        """
        try:
            renamed = rename_object_id(self.toPlainText(), self.textCursor().blockNumber() + 1, new_id)
        except ValueError as ex:
            return str(ex)
        if renamed.text != self.toPlainText():
            self._replace_text(renamed.text)
        return None

    def _replace_text(self, text: str):
        """Replace the text as one edit that can be undone; the cursor and the view stay where they were."""
        cursor = self.textCursor()
        line, column = cursor.blockNumber(), cursor.positionInBlock()
        scroll = self.verticalScrollBar().value()
        self.unfold_all()
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        edit.select(QTextCursor.SelectionType.Document)
        edit.insertText(text)
        edit.endEditBlock()
        block = self.document().findBlockByNumber(min(line, self.document().blockCount() - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(column, max(block.length() - 1, 0)))
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(scroll)

    # --- links, documentation, menu ---

    # --- colors ---

    def edit_color(self, block_number: int, token: Token):
        """Open the color picker for the color string (with its quotes) at a place of the text."""
        self._colors.edit(block_number, token)

    def set_definition_finder(self, finder: Callable[[str], Optional[Definition]]):
        """Where a variable of a template is defined: only the parts of variables that are found can be Ctrl+clicked."""
        self._find_definition = finder

    def _link_at(self, position) -> Optional[Tuple[int, Link]]:
        cursor = self.cursorForPosition(position)
        text, column = cursor.block().text(), cursor.positionInBlock()
        link = link_at(text, column, self.language)
        if link is None and self.language == Language.YAML:
            key = key_at(self.toPlainText(), cursor.blockNumber() + 1, column)
            link = None if key is None else Link(key.start, key.end, key.name, kind="usages")
        elif link is None and self.language != Language.TEXT:
            part = part_at(text, column)
            if part is not None and self._find_definition(part.name) is not None:
                link = Link(part.start, part.end, part.name, kind="variable")
        return None if link is None else (cursor.blockNumber(), link)

    def _set_hover_link(self, found: Optional[Tuple[int, Link]]):
        if found == self._hover_link:
            return
        self._hover_link = found
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor if found is None else Qt.CursorShape.PointingHandCursor)
        self._update_selections()

    def _link_selections(self) -> List[QTextEdit.ExtraSelection]:
        if self._hover_link is None:
            return []
        number, link = self._hover_link
        block = self.document().findBlockByNumber(number)
        selection = QTextEdit.ExtraSelection()
        selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        selection.format.setForeground(self.palette().color(QPalette.ColorRole.Link))
        selection.cursor = QTextCursor(self.document())
        selection.cursor.setPosition(block.position() + link.start)
        selection.cursor.setPosition(block.position() + link.end, QTextCursor.MoveMode.KeepAnchor)
        return [selection]

    def mouseMoveEvent(self, event):
        control = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._set_hover_link(self._link_at(event.position().toPoint()) if control else None)
        self._hover_position = event.position().toPoint()
        if self._hover_card.isVisible() and self._tip_area.contains(self._hover_position):
            self._hover_grace_timer.stop()
        else:
            self._hover_timer.start()
            if self._hover_card.isVisible():
                self._hover_grace_timer.start()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        if self._hover_card.isVisible():
            self._hover_grace_timer.start()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            color = self._colors.color_at(event.position().toPoint())
            if color is not None:
                self.edit_color(*color)
                event.accept()
                return
        found = self._link_at(event.position().toPoint())
        if (
            found is not None
            and event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            link = found[1]
            if link.kind == "usages":
                self.usagesRequested.emit(link.target, event.globalPosition().toPoint())
            else:
                (self.definitionRequested if link.kind == "variable" else self.linkRequested).emit(link.target)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self._set_hover_link(None)
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu: QMenu = self.createStandardContextMenu()
        menu.addSeparator()
        color = self._colors.color_at(event.pos())
        if color is not None:
            action = QAction("Edit color…\tCtrl+click", menu)
            action.triggered.connect(lambda _checked=False, color=color: self.edit_color(*color))
            menu.addAction(action)
            menu.addSeparator()
        for text, handler in (
            ("Format document\tCtrl+Alt+L", self.format_document),
            ("Rename id…\tShift+F6", self.renameRequested.emit),
            ("Fold\tCtrl+-", self.fold_at_cursor),
            ("Unfold\tCtrl+=", self.unfold_at_cursor),
            ("Fold all", self.fold_all),
            ("Unfold all", self.unfold_all),
        ):
            action = QAction(text, menu)
            action.triggered.connect(lambda _checked=False, handler=handler: handler())
            action.setEnabled(self.language != Language.TEXT)
            menu.addAction(action)
        menu.exec(event.globalPos())

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
        self.end_flash()
        self._hide_hover_card()
        popup = self._completer.popup()
        key = event.key()
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if popup.isVisible() and key in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Escape,
            Qt.Key.Key_Backtab,
        ):
            event.ignore()
            return
        if control and alt and key == Qt.Key.Key_L:
            self.format_document()
        elif key == Qt.Key.Key_F6 and shift:
            self.renameRequested.emit()
        elif control and key == Qt.Key.Key_Minus:
            self.fold_at_cursor()
        elif control and key == Qt.Key.Key_Underscore:
            self.fold_all()
        elif control and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.unfold_all() if alt else self.unfold_at_cursor()
        elif control and key == Qt.Key.Key_S:
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
        line_number = self.textCursor().blockNumber() + 1
        found = object_at_line(self.objects(), line_number)
        context = completion_context(before, self.language, inside_object=found is not None)
        if context is None:
            self._completer.popup().hide()
            return
        self._completion_kind = context.kind
        self._completion_context = context
        self._completion_object_type = object_type_at_line(self.objects(), line_number)
        present = [prop.key for prop in found.properties] if found is not None else []
        properties = properties_for(self._completion_object_type, context.prefix, present)
        words = complete(context, properties, self._variables())
        if not words or (not force and not context.prefix):
            self._completer.popup().hide()
            return
        self._completer.model().setStringList(words)
        self._completer.setCompletionPrefix(context.prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 8)
        self._completer.complete(rect)
        self._show_completion_docs(words[0] if words else "")

    def _show_completion_docs(self, word: str):
        """Shows what the highlighted entry of the completion list is, next to the list."""
        popup = self._completer.popup()
        found = property_help(word, self._completion_object_type) if self._completion_kind == "property" else None
        if found is None or not popup.isVisible():
            self._completion_card.hide()
            return
        if popup is not self._watched_popup:
            # the completer makes its list when it needs it, so it can only be watched once it shows
            self._watched_popup = popup
            _HideWith(popup, self._completion_card)
        self._completion_card.show_beside(popup, CardContent(help=found))

    def _insert_completion(self, word: str):
        cursor = self.textCursor()
        block = cursor.block()
        context = self._completion_context
        if self._completion_kind == "property":
            line, column = block.text(), cursor.positionInBlock()
            insertion = property_insertion(line, column, context, word, self._completion_object_type)
            start, end, text, after = insertion.start, insertion.end, insertion.text, insertion.cursor
        else:
            start, end, text = context.start, cursor.positionInBlock(), word
            after = start + len(text)
        cursor.beginEditBlock()
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        cursor.setPosition(block.position() + after)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
