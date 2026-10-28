from PyQt6 import QtCore
from PyQt6.QtCore import QObject, QPoint, QRect
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from openhasp_config_manager.gui.domain.source.docs import help_at, theme_help_at
from openhasp_config_manager.gui.domain.source.syntax import Language
from openhasp_config_manager.gui.qt.widgets.hover_card import CardContent, HoverCard

# how long the mouse has to rest on a property before its explanation shows (the default of Qt is about 700 ms)
_HOVER_DELAY_MS = 120
# how long the card stays when the mouse left the property and did not reach the card yet
_HOVER_GRACE_MS = 300


class EditorHover(QObject):
    """
    The card of a text editor with the problems of a line and the explanation of the property or variable under the mouse: it
    shows soon after the mouse came to rest, and stays while the mouse is on the property or on the card, so its text can be
    selected and copied.
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_HOVER_DELAY_MS)
        self._timer.timeout.connect(self._show)
        self._position = QPoint()
        self.card = HoverCard(editor, interactive=True)
        self.card.mouseEntered.connect(lambda: self.grace_timer.stop())
        self.card.mouseLeft.connect(lambda: self.grace_timer.start())
        self.grace_timer = QtCore.QTimer(self)
        self.grace_timer.setSingleShot(True)
        self.grace_timer.setInterval(_HOVER_GRACE_MS)
        self.grace_timer.timeout.connect(self.hide)
        # what the card is about, in the coordinates of the viewport: moving inside of it keeps the card
        self.tip_area = QRect()
        editor.verticalScrollBar().valueChanged.connect(lambda _value: self.hide())

    def card_content_at(self, position: QPoint) -> CardContent:
        """:return: the problems of the line and the explanation of the property, at a position of the viewport"""
        editor = self._editor
        cursor = editor.cursorForPosition(position)
        line = cursor.blockNumber() + 1
        issues = [(marker.severity, marker.message) for marker in editor.markers_at(line) + editor.hints_at(line)]
        found = None
        if editor.language == Language.JSONL:
            found = help_at(editor.objects(), cursor.block().text(), cursor.blockNumber() + 1, cursor.positionInBlock())
            if found is None:
                found = editor.values.help_at(cursor.block().text(), cursor.positionInBlock())
        elif editor.language == Language.YAML:
            found = theme_help_at(editor.toPlainText(), cursor.blockNumber() + 1, cursor.positionInBlock())
        return CardContent(issues, found)

    def tip_area_at(self, position: QPoint) -> QRect:
        """:return: the area of the viewport the card at a position is about (a word, or the line for an issue)"""
        editor = self._editor
        cursor = editor.cursorForPosition(position)
        line = cursor.blockNumber() + 1
        if (editor.markers_at(line) or editor.hints_at(line)) and not self.card_content_at(position).help:
            return editor.blockBoundingGeometry(cursor.block()).translated(editor.contentOffset()).toRect()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        first, last = QTextCursor(cursor), QTextCursor(cursor)
        first.setPosition(cursor.selectionStart())
        last.setPosition(cursor.selectionEnd())
        return editor.cursorRect(first).united(editor.cursorRect(last))

    def mouse_moved(self, position: QPoint):
        """The mouse moved over the viewport."""
        self._position = position
        if self.card.isVisible() and self.tip_area.contains(position):
            self.grace_timer.stop()
        else:
            self._timer.start()
            if self.card.isVisible():
                self.grace_timer.start()

    def mouse_left(self):
        """The mouse left the viewport."""
        self._timer.stop()
        if self.card.isVisible():
            self.grace_timer.start()

    def _show(self):
        editor = self._editor
        position = self._position
        if not editor.viewport().underMouse():
            return
        content = self.card_content_at(position)
        if content.is_empty():
            self.grace_timer.start()
            return
        area = self.tip_area_at(position)
        key = (editor.cursorForPosition(position).blockNumber(), area.left(), area.right())
        self.grace_timer.stop()
        if self.card.isVisible() and self.card.key == key:
            return
        self.tip_area = area
        anchor = QRect(editor.viewport().mapTo(editor, area.topLeft()), area.size())
        self.card.show_content(content, anchor, key)

    def hide(self):
        self._timer.stop()
        self.grace_timer.stop()
        self.tip_area = QRect()
        self.card.hide()
