from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    fraction,
    number,
    polar,
    scale_start,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ANGLE = 240
_DEFAULT_LINE_COUNT = 31
_DEFAULT_LINE_WIDTH = 3
_INACTIVE = "#808080"
# how long a line is, relative to the radius
_LINE_LENGTH = 0.2


class HaspLineMeterItem(EditableWidget):
    """
    `line_count` lines around `angle` degrees (rotated by `rotation`); the lines up to `val` are drawn in the indicator color.
    `type` 0 activates the lines clockwise, 1 counter-clockwise.
    See https://www.openhasp.com/0.7.0/design/objects/linemeter/
    """

    def active_lines(self) -> int:
        count = int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT))
        return round(fraction(self.obj_data.get("val", 0), self.obj_data.get("min", 0), self.obj_data.get("max", 100)) * count)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        count = max(int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT)), 1)
        angle = number(self.obj_data.get("angle"), _DEFAULT_ANGLE)
        start = scale_start(angle, number(self.obj_data.get("rotation"), 0))
        width = number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH)
        radius = min(self.obj_w, self.obj_h) / 2 - width
        center = self.obj_rect.center()
        active, reverse = self.active_lines(), int(number(self.obj_data.get("type"), 0)) == 1
        inactive_color = to_color(self.style("line_color"), _INACTIVE)
        active_color = to_color(self.style("line_color", DEFAULT_ACCENT, Part.INDICATOR), DEFAULT_ACCENT)

        for line in range(count):
            is_active = line >= count - active if reverse else line < active
            pen = QtGui.QPen(active_color if is_active else inactive_color, width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            degrees = start + angle * line / max(count - 1, 1)
            painter.drawLine(polar(center, radius, degrees), polar(center, radius * (1 - _LINE_LENGTH), degrees))
        super().paint(painter, option, widget)
