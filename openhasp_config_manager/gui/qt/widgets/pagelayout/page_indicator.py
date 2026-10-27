from typing import Dict, List

from PyQt6 import QtCore
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

from openhasp_config_manager.gui.domain.page_objects import page_label
from openhasp_config_manager.gui.qt.theme import current_colors

SEGMENT_WIDTH = 16
SEGMENT_HEIGHT = 6
GAP = 3
# the space left and right, to line up with the buttons of the bar
PAD = 10
# between the global page and the pages of the plate
GLOBAL_GAP = 8


class PageIndicator(QWidget):
    """A segmented bar with a segment per page, the current one highlighted and the ones without objects dimmed."""

    # a segment was clicked: the page
    pageClicked = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: List[int] = []
        self._current = -1
        self._counts: Dict[int, int] = {}
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SEGMENT_HEIGHT + GAP)

    def set_state(self, pages: List[int], current: int, objects_per_page: Dict[int, int]):
        """
        :param pages: all pages, in the order of the bar (the global page 0 first)
        :param objects_per_page: the number of objects of each page that has some
        """
        self._pages, self._current, self._counts = pages, current, objects_per_page
        self.setFixedWidth(int(self._segment(len(pages) - 1).right()) + PAD + 1 if pages else 0)
        self.update()

    def _segment(self, index: int) -> QRectF:
        x = PAD + index * (SEGMENT_WIDTH + GAP) + (GLOBAL_GAP - GAP if index > 0 and self._pages[0] == 0 else 0)
        return QRectF(x, GAP / 2, SEGMENT_WIDTH, SEGMENT_HEIGHT)

    def _index_at(self, position: QPointF) -> int:
        for index in range(len(self._pages)):
            # the gaps belong to the segment before them, so every click hits a page
            rect = self._segment(index)
            if rect.left() - GAP <= position.x() <= rect.right() + GAP / 2:
                return index
        return -1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.WindowText)
        for index, page in enumerate(self._pages):
            rect = self._segment(index)
            if page == self._current:
                color = QColor(current_colors().accent)
            elif self._counts.get(page):
                color = QColor(text)
                color.setAlpha(150)
            else:
                color = QColor(text)
                color.setAlpha(45)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, SEGMENT_HEIGHT / 2, SEGMENT_HEIGHT / 2)
            if page == 0 and page != self._current:
                # the global page is no page of the plate: an outline instead of a fill
                painter.setBrush(Qt.BrushStyle.NoBrush)
                color.setAlpha(120)
                painter.setPen(QPen(color, 1))
                painter.drawRoundedRect(rect, SEGMENT_HEIGHT / 2, SEGMENT_HEIGHT / 2)

    def _description(self, page: int) -> str:
        count = self._counts.get(page, 0)
        return f"{page_label(page)}: {count} object{'' if count == 1 else 's'}" if count else f"{page_label(page)}: empty"

    def mouseMoveEvent(self, event: QMouseEvent):
        index = self._index_at(event.position())
        if index >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), self._description(self._pages[index]), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event: QMouseEvent):
        index = self._index_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and index >= 0:
            self.pageClicked.emit(self._pages[index])
