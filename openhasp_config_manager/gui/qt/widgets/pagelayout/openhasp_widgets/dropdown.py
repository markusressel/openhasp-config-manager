from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_TEXT,
    DEFAULT_TRACK,
    draw_text,
    number,
    option_lines,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_PADDING = 10
_ARROW_SIZE = 5


class HaspDropdownItem(EditableWidget):
    """
    A closed dropdown: the selected entry of `options` (by `val`) and an arrow. The open list is not drawn.
    See https://www.openhasp.com/0.7.0/design/objects/dropdown/
    """

    @property
    def selected_text(self) -> str:
        options = option_lines(self.obj_data.get("options"))
        index = int(number(self.obj_data.get("val"), 0))
        return options[index] if 0 <= index < len(options) else ""

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        radius = number(self.style("radius", 4), 4)
        painter.setBrush(to_color(self.style("bg_color"), DEFAULT_TRACK))
        painter.setPen(QtGui.QPen(to_color(self.style("border_color"), "#808080"), number(self.style("border_width", 1), 1)))
        painter.drawRoundedRect(self.obj_rect, radius, radius)

        text_rect = self.obj_rect.adjusted(_PADDING, 0, -(_PADDING * 3), 0)
        draw_text(
            painter,
            text_rect,
            self.selected_text,
            to_color(self.style("text_color"), DEFAULT_TEXT),
            plate_font(self.style("text_font", 25)),
            "left",
        )

        # the arrow points in the direction the list opens (0 down, 1 up, 2 left, 3 right)
        center = QtCore.QPointF(self.obj_w - _PADDING * 1.5, self.obj_h / 2)
        direction = int(number(self.obj_data.get("direction"), 0))
        dx, dy = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}.get(direction, (0, 1))
        tip = center + QtCore.QPointF(dx, dy) * _ARROW_SIZE
        back = center - QtCore.QPointF(dx, dy) * _ARROW_SIZE
        side = QtCore.QPointF(-dy, dx) * _ARROW_SIZE
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(to_color(self.style("text_color"), DEFAULT_TEXT))
        painter.drawPolygon(QtGui.QPolygonF([tip, back + side, back - side]))
        super().paint(painter, option, widget)
