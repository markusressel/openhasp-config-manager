from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QColor, QPainter, QPalette, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from openhasp_config_manager.gui.domain.colors import Argb
from openhasp_config_manager.gui.domain.source.docs import PropertyHelp
from openhasp_config_manager.gui.domain.source.syntax import Language
from openhasp_config_manager.gui.domain.variables.template_values import line_colors, line_values, variable_help

# how many colors of a line a swatch shows
_SWATCH_COLORS = 3


class EditorValues(QObject):
    """
    What the variables and templates of a text editor are in the draft: shown in the card of the hover, as values after the
    line (optional) and as color swatches in the gutter.
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        # the value of a variable (KeyError if it has none) and what a text with templates renders to, in the draft
        self._variable_value: Optional[Callable[[str], Any]] = None
        self._render_text: Optional[Callable[[str], Optional[str]]] = None
        self._show = False
        # line -> what its templates render to ([] if nothing), for the values next to the text
        self._values_cache: Dict[str, List[str]] = {}
        self._colors_cache: Dict[str, List[Argb]] = {}
        # template -> what it renders to
        self._rendered: Dict[str, Optional[str]] = {}

    def set_source(self, variable_value: Callable[[str], Any], render_text: Callable[[str], Optional[str]]):
        """What the variables and templates of the text are: for the hover card, the values next to the text and the swatches."""
        self._variable_value = variable_value
        self._render_text = render_text
        self.refresh()

    def refresh(self):
        """The variables changed: show the values again."""
        self._values_cache.clear()
        self._colors_cache.clear()
        self._rendered.clear()
        self._editor.viewport().update()
        self._editor.gutter.update()

    def set_show(self, show: bool):
        """Show what the templates of a line render to after the line, in grey."""
        self._show = show
        self._editor.viewport().update()

    def help_at(self, line: str, column: int) -> Optional[PropertyHelp]:
        """:return: the value of the variable at a column of a line, None if there is no source of values or it is no variable"""
        if self._variable_value is None:
            return None
        return variable_help(line, column, self._variable_value, self._render_text)

    def _render(self, text: str) -> Optional[str]:
        """Renders a template, once (until the values are refreshed): the values and the colors of a line need it both."""
        if text not in self._rendered:
            self._rendered[text] = self._render_text(text)
        return self._rendered[text]

    def _values_of(self, line: str) -> List[str]:
        if "{{" not in line:
            return []
        if line not in self._values_cache:
            self._values_cache[line] = line_values(line, self._render)
        return self._values_cache[line]

    def colors_of(self, line: str) -> List[Argb]:
        if line not in self._colors_cache:
            self._colors_cache[line] = line_colors(
                line, self._editor.language, None if self._render_text is None else self._render
            )
        return self._colors_cache[line]

    def paint_swatch(self, painter: QPainter, line: str, top: int, height: int):
        """A small square with the colors of a line (side by side, at most `_SWATCH_COLORS`), right of the issue marker."""
        colors = self.colors_of(line)[:_SWATCH_COLORS]
        if not colors:
            return
        size = height - 4
        x, y = 4 + height // 2 + 3, top + 2
        painter.setPen(Qt.PenStyle.NoPen)
        for index, argb in enumerate(colors):
            left, right = x + size * index // len(colors), x + size * (index + 1) // len(colors)
            painter.setBrush(QColor(argb.red, argb.green, argb.blue, argb.alpha))
            painter.drawRect(left, y, right - left, size)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self._editor.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.drawRect(x, y, size, size)

    def paint_values(self, painter: QPainter, rect):
        """Draws the values of the visible lines after them, if they are shown. :param rect: the area to paint"""
        editor = self._editor
        if not self._show or self._render_text is None or editor.language != Language.JSONL:
            return
        palette = editor.palette()
        color = QColor(palette.color(QPalette.ColorRole.Text))
        color.setAlpha(170)
        painter.setPen(color)
        font = painter.font()
        font.setItalic(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width_of_view = editor.viewport().width()
        block = editor.firstVisibleBlock()
        while block.isValid():
            top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
            if top > rect.bottom():
                break
            if block.isVisible() and (values := self._values_of(block.text())):
                end = QTextCursor(block)
                end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                line_rect = editor.cursorRect(end)
                text = "= " + " · ".join(values)
                width = metrics.horizontalAdvance(text)
                x = line_rect.right() + 16
                if x + width + 8 > width_of_view:
                    # the line goes beyond the window: the values stay in sight at its edge, over the text
                    x = max(width_of_view - width - 8, 0)
                    painter.fillRect(
                        x - 6, line_rect.top(), width + 12, line_rect.height(), palette.color(QPalette.ColorRole.AlternateBase)
                    )
                painter.drawText(x, line_rect.top() + metrics.ascent(), text)
            block = block.next()
