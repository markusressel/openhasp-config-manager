import re
from typing import Callable, List, Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import QPoint, QRect, QRectF, QSettings, QSize, Qt
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFontDatabase,
    QKeyEvent,
    QPainter,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextOption,
)
from PyQt6.QtWidgets import QMenu, QPlainTextEdit, QTextEdit, QWidget

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source.edit import INDENT, matching_bracket
from openhasp_config_manager.gui.domain.source.issues import SourceIssue, find_source_issues
from openhasp_config_manager.gui.domain.source.links import Link, link_at
from openhasp_config_manager.gui.domain.source.objects import SourceObject, object_at_line, scan_objects
from openhasp_config_manager.gui.domain.source.syntax import Language, Token, TokenKind, tokenize_line
from openhasp_config_manager.gui.domain.variables.definitions import Definition, key_at
from openhasp_config_manager.gui.domain.variables.references import part_at
from openhasp_config_manager.gui.qt.widgets.hover_card import MODIFIER_KEYS
from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import SourceHighlighter
from openhasp_config_manager.gui.qt.widgets.code_editor.colors import EditorColors
from openhasp_config_manager.gui.qt.widgets.code_editor.completion import EditorCompletion
from openhasp_config_manager.gui.qt.widgets.code_editor.edits import PAIRS, EditorEdits
from openhasp_config_manager.gui.qt.widgets.code_editor.folding import EditorFolding
from openhasp_config_manager.gui.qt.widgets.code_editor.hover import EditorHover
from openhasp_config_manager.gui.qt.widgets.code_editor.search import EditorSearch
from openhasp_config_manager.gui.qt.widgets.code_editor.values import EditorValues
from openhasp_config_manager.gui.qt.theme import current_colors

_FONT_SIZE_KEY = "editor/font_size"
_DEFAULT_FONT_SIZE = 10
_ISSUE_DELAY_MS = 300
_FOLD_WIDTH = 14
# how long `flash_lines` highlights lines
FLASH_MS = 3000
# the opacity of the text of lines with a hint, 0..255
_HINT_ALPHA = 110
# the opacity of the background of flashed lines, 0..255
_CURRENT_LINE_ALPHA = 28
_FLASH_ALPHA = 80
_CODE = re.compile(r"`([^`]+)`")


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
        self._editor.folding.gutter_clicked(round(event.position().y()))


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
        self._find_definition: Callable[[str], Optional[Definition]] = lambda name: None
        self.search = EditorSearch(self)
        self.folding = EditorFolding(self)
        self.edits = EditorEdits(self)
        self.values = EditorValues(self)
        self.completion = EditorCompletion(self)
        self._colors = EditorColors(self, language)
        self._picker = self._colors.picker
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
        self.gutter = _Gutter(self)

        self.hover = EditorHover(self)

        self._issue_timer = QtCore.QTimer(self)
        self._issue_timer.setSingleShot(True)
        self._issue_timer.setInterval(_ISSUE_DELAY_MS)
        self._issue_timer.timeout.connect(self.update_issues)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.blockCountChanged.connect(lambda _count: self.folding.unfold_all())
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self.update_selections)
        self.textChanged.connect(self._on_text_changed)
        self._update_gutter_width()
        self.update_selections()

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
        self.update_selections()
        self.textEdited.emit()

    # --- issues and markers ---

    @property
    def issues(self) -> List[SourceIssue]:
        return list(self._text_markers)

    def update_issues(self):
        """Look at the text for problems now (otherwise a moment after the last edit)."""
        self._issue_timer.stop()
        self._text_markers = find_source_issues(self.toPlainText(), self.language)
        self.update_selections()
        self.gutter.update()
        self.issuesChanged.emit()

    def set_app_markers(self, markers: List[SourceIssue]):
        """Problems found by the app for the objects of this file (e.g. one is outside of the screen)."""
        self._app_markers = list(markers)
        self.update_selections()
        self.gutter.update()

    def set_hints(self, hints: List[SourceIssue]):
        """Things worth knowing about lines, that are no problems (e.g. a variable that is not used): dimmed, explained on hover."""
        self._hints = list(hints)
        self.update_selections()

    def hints_at(self, line: int) -> List[SourceIssue]:
        return [hint for hint in self._hints if hint.line == line]

    def _markers(self) -> List[SourceIssue]:
        return self._text_markers + self._app_markers

    def markers_at(self, line: int) -> List[SourceIssue]:
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
        self.update_selections()
        self.gutter.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    # --- gutter ---

    def gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 20 + _FOLD_WIDTH + self.fontMetrics().height() + self.fontMetrics().horizontalAdvance("9") * max(digits, 2)

    def _update_gutter_width(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self.gutter.setGeometry(QRect(area.left(), area.top(), self.gutter_width(), area.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        palette = self.palette()
        painter.fillRect(event.rect(), palette.color(QPalette.ColorRole.AlternateBase))
        current = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        fold_starts = {start for start, _ in self.folding.ranges()}
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            if block.isVisible() and bottom >= event.rect().top():
                markers = self.markers_at(number + 1)
                if markers:
                    worst = Severity.ERROR if any(m.severity == Severity.ERROR for m in markers) else Severity.WARNING
                    painter.setBrush(_marker_color(worst))
                    painter.setPen(Qt.PenStyle.NoPen)
                    size = height // 2
                    painter.drawEllipse(4, top + (height - size) // 2, size, size)
                self.values.paint_swatch(painter, block.text(), top, height)
                font = painter.font()
                font.setBold(number == current)
                painter.setFont(font)
                painter.setPen(
                    palette.color(QPalette.ColorRole.WindowText if number == current else QPalette.ColorRole.PlaceholderText)
                )
                painter.drawText(
                    0, top, self.gutter.width() - 6 - _FOLD_WIDTH, height, Qt.AlignmentFlag.AlignRight, str(number + 1)
                )
                if number + 1 in fold_starts:
                    painter.drawText(
                        self.gutter.width() - _FOLD_WIDTH - 2,
                        top,
                        _FOLD_WIDTH,
                        height,
                        Qt.AlignmentFlag.AlignCenter,
                        "▸" if self.folding.is_folded(number + 1) else "▾",
                    )
            block = block.next()
            top = bottom
            number += 1

    # --- selections: current line, brackets, issues, search ---

    def update_selections(self):
        selections: List[QTextEdit.ExtraSelection] = []
        selections += self._bracket_selections()
        selections += self._marker_selections()
        selections += self._hint_selections()
        selections += self.search.selections()
        selections += self._link_selections()
        selections += self._flash_selections()
        self.setExtraSelections(selections)
        self.folding.reveal_cursor()
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
        """Dims the text of a hint (italic, and less opaque). A color string keeps its color: dimmed, it can't be read on it."""
        color = self.palette().color(QPalette.ColorRole.Text)
        color.setAlpha(_HINT_ALPHA)
        result = []
        for hint in self._hints:
            block = self.document().findBlockByNumber(hint.line - 1)
            if not block.isValid():
                continue
            start = min(hint.column, max(block.length() - 1, 0))
            end = min(start + hint.length, block.length() - 1)
            colors = [
                (token.start, token.end)
                for token in tokenize_line(block.text(), self.language)
                if token.kind == TokenKind.COLOR
            ]
            # the parts of the hint outside of color strings, then the color strings in it
            edges = sorted({start, end, *(edge for span in colors for edge in span if start < edge < end)})
            for left, right in zip(edges, edges[1:]):
                is_color = any(first <= left and right <= last for first, last in colors)
                selection = QTextEdit.ExtraSelection()
                if not is_color:
                    selection.format.setForeground(color)
                selection.format.setFontItalic(True)
                selection.cursor = QTextCursor(self.document())
                selection.cursor.setPosition(block.position() + left)
                selection.cursor.setPosition(block.position() + right, QTextCursor.MoveMode.KeepAnchor)
                result.append(selection)
        return result

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            # the card of the hover replaces the tool tip, which comes late and goes away when the mouse moves
            return True
        return super().event(event)

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
        self.update_selections()

    def end_flash(self):
        if self._flash is None:
            return
        self._flash = None
        self._flash_timer.stop()
        self.update_selections()

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
        self.hover.hide()
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

    # --- colors, links, menu ---

    def edit_color(self, block_number: int, token: Token):
        """Open the color picker for the color string (with its quotes) at a place of the text."""
        self._colors.edit(block_number, token)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        self._paint_current_line(painter)
        self.values.paint_values(painter, event.rect())
        painter.end()

    def _paint_current_line(self, painter: QPainter):
        """
        Tints the line of the cursor. It is drawn over the text, not as a selection: a selection replaces the background of the
        text, which hides the color of a color string (readable text on it needs that color).
        """
        color = self.palette().color(QPalette.ColorRole.Highlight)
        color.setAlpha(_CURRENT_LINE_ALPHA)
        block = self.textCursor().block()
        rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        painter.fillRect(QRectF(0, rect.top(), self.viewport().width(), rect.height()), color)

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
        self.update_selections()

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
        self.hover.mouse_moved(event.position().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover.mouse_left()
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
            ("Format document\tCtrl+Alt+L", self.edits.format_document),
            ("Rename id…\tShift+F6", self.renameRequested.emit),
            ("Fold\tCtrl+-", self.folding.fold_at_cursor),
            ("Unfold\tCtrl+=", self.folding.unfold_at_cursor),
            ("Fold all", self.folding.fold_all),
            ("Unfold all", self.folding.unfold_all),
        ):
            action = QAction(text, menu)
            action.triggered.connect(lambda _checked=False, handler=handler: handler())
            action.setEnabled(self.language != Language.TEXT)
            menu.addAction(action)
        menu.exec(event.globalPos())

    # --- keys ---

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() not in MODIFIER_KEYS:
            self.end_flash()
            self.hover.hide()
        popup = self.completion.popup
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
            self.edits.format_document()
        elif key == Qt.Key.Key_F6 and shift:
            self.renameRequested.emit()
        elif control and key == Qt.Key.Key_Minus:
            self.folding.fold_at_cursor()
        elif control and key == Qt.Key.Key_Underscore:
            self.folding.fold_all()
        elif control and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.folding.unfold_all() if alt else self.folding.unfold_at_cursor()
        elif control and key == Qt.Key.Key_S:
            self.saveRequested.emit()
        elif control and key == Qt.Key.Key_F:
            self.findRequested.emit()
        elif control and key == Qt.Key.Key_Slash:
            self.edits.toggle_comment()
        elif control and key == Qt.Key.Key_D:
            self.edits.duplicate_lines()
        elif control and key == Qt.Key.Key_Space:
            self.completion.show(force=True)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not control:
            self.edits.new_line()
        elif key == Qt.Key.Key_Tab and not control:
            self.edits.indent(True)
        elif key == Qt.Key.Key_Backtab:
            self.edits.indent(False)
        elif key == Qt.Key.Key_Backspace and not modifiers and self.edits.delete_pair():
            pass
        elif event.text() in PAIRS.values() and not control and self.edits.type_over(event.text()):
            pass
        elif event.text() in PAIRS and not control and self.edits.type_pair(event.text()):
            pass
        else:
            super().keyPressEvent(event)
            if event.text() and (event.text().isalnum() or event.text() in '_."{'):
                self.completion.show()
            elif popup.isVisible():
                popup.hide()
