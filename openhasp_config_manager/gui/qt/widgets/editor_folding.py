from typing import List, Set, Tuple

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from openhasp_config_manager.gui.domain.source_objects import foldable


class EditorFolding(QObject):
    """Folds the objects of a .jsonl text editor: the lines between the brackets of an object are hidden."""

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        # the first lines of the folded objects
        self._folded: Set[int] = set()

    def ranges(self) -> List[Tuple[int, int]]:
        """:return: (first line, last line) of the objects that can be folded; the lines in between are hidden when folded"""
        return foldable(self._editor.objects())

    def is_folded(self, line: int) -> bool:
        return line in self._folded

    def fold(self, line: int) -> bool:
        """Hide the lines of the object that starts at a line (starts at 1). :return: whether there is such an object"""
        return self._set_folded(line, True)

    def unfold(self, line: int) -> bool:
        return self._set_folded(line, False)

    def toggle(self, line: int) -> bool:
        return self._set_folded(line, line not in self._folded)

    def fold_at_cursor(self):
        """Fold the object of the cursor."""
        found = self._editor.object_at_cursor()
        if found is not None:
            self.fold(found.start_line)
            if self._editor.textCursor().blockNumber() + 1 > found.start_line:
                self._move_cursor_to_line(found.start_line)

    def unfold_at_cursor(self):
        found = self._editor.object_at_cursor()
        if found is not None:
            self.unfold(found.start_line)

    def fold_all(self):
        for start, _ in self.ranges():
            self.fold(start)
        found = self._editor.object_at_cursor()
        if found is not None:
            self._move_cursor_to_line(found.start_line)

    def unfold_all(self):
        for start in sorted(self._folded):
            self._set_folded(start, False)

    def _set_folded(self, line: int, folded: bool) -> bool:
        end = next((end for start, end in self.ranges() if start == line), None)
        if end is None:
            return False
        if folded:
            self._folded.add(line)
        else:
            self._folded.discard(line)
        document = self._editor.document()
        # the lines between the brackets: the first and the last stay visible
        for number in range(line + 1, end):
            block = document.findBlockByNumber(number - 1)
            if block.isValid():
                block.setVisible(not folded)
        first = document.findBlockByNumber(line - 1)
        document.markContentsDirty(first.position(), document.characterCount() - first.position())
        self._editor.viewport().update()
        self._editor.gutter.update()
        return True

    def reveal_cursor(self):
        """Unfold what hides the cursor (it was moved into a folded object by a search, a jump to an error, ...)."""
        if not self._folded or self._editor.textCursor().block().isVisible():
            return
        line = self._editor.textCursor().blockNumber() + 1
        for start, end in self.ranges():
            if start in self._folded and start < line < end:
                self.unfold(start)

    def _move_cursor_to_line(self, line: int):
        editor = self._editor
        block = editor.document().findBlockByNumber(line - 1)
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(editor.textCursor().positionInBlock(), max(block.length() - 1, 0)))
        editor.setTextCursor(cursor)

    def gutter_clicked(self, y: int):
        """A click in the gutter folds or unfolds the object that starts in that line."""
        editor = self._editor
        block = editor.firstVisibleBlock()
        top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        while block.isValid():
            bottom = top + round(editor.blockBoundingRect(block).height())
            if block.isVisible() and top <= y < bottom:
                self.toggle(block.blockNumber() + 1)
                return
            if top > y:
                return
            block = block.next()
            top = bottom
