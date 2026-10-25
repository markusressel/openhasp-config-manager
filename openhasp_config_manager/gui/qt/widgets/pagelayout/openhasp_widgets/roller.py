from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TEXT,
    DEFAULT_TRACK,
    draw_text,
    number,
    option_lines,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ROWS = 3
_ROW_SPACING = 12


class HaspRollerItem(EditableWidget):
    """
    A list that shows `rows` entries of `options` with the selected one (`val`) in the middle, highlighted. The height follows
    `rows` and the font (`h` is ignored). In mode 1 (infinite) the list wraps around.
    See https://www.openhasp.com/0.7.0/design/objects/roller/
    """

    @property
    def rows(self) -> int:
        return max(int(number(self.obj_data.get("rows"), _DEFAULT_ROWS)), 1)

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", 25))

    @property
    def row_height(self) -> int:
        return QtGui.QFontMetrics(self.font).height() + _ROW_SPACING

    @property
    def obj_h(self) -> int:
        return self.rows * self.row_height

    def visible_entries(self) -> list:
        """:return: the entry of every visible row (None for rows without one), the selected entry in the middle"""
        options = option_lines(self.obj_data.get("options"))
        selected = int(number(self.obj_data.get("val"), 0))
        infinite = int(number(self.obj_data.get("mode"), 0)) == 1
        entries = []
        for row in range(self.rows):
            index = selected + row - self.rows // 2
            if infinite and options:
                index %= len(options)
            entries.append(options[index] if 0 <= index < len(options) else None)
        return entries

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        radius = number(self.style("radius", 4), 4)
        painter.setBrush(to_color(self.style("bg_color"), DEFAULT_TRACK))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.obj_rect, radius, radius)

        # the selected row
        middle = (self.rows // 2) * self.row_height
        painter.setBrush(to_color(self.style("bg_color", DEFAULT_ACCENT, Part.SELECTED), DEFAULT_ACCENT))
        painter.drawRect(QtCore.QRectF(0, middle, self.obj_w, self.row_height))

        align = self.obj_data.get("align", "center")
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        for row, entry in enumerate(self.visible_entries()):
            if entry is None:
                continue
            row_color = QtGui.QColor(color)
            if row != self.rows // 2:
                row_color.setAlpha(150)
            draw_text(
                painter,
                QtCore.QRectF(8, row * self.row_height, self.obj_w - 16, self.row_height),
                entry,
                row_color,
                self.font,
                align,
            )
        super().paint(painter, option, widget)
