from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.meter_geometry import active_lines, value_fraction
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import DISC_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_SCALE_ANGLE,
    mix,
    number,
    polar,
    scale_start,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_LINE_COUNT = 18
_DEFAULT_LINE_WIDTH = 4.15
# measured on a plate: gray lines, the active ones blue, on a round track
_INACTIVE = "#8B898B"
_ACTIVE = "#00B6FF"
# measured on a plate, whatever the size: the lines end this far from the edge, and are this long
_LINE_INSET = 13
_LINE_LENGTH = 16


class HaspLineMeterItem(EditableWidget):
    """
    `line_count` lines around `angle` degrees (rotated by `rotation`); the lines up to `val` are drawn in the indicator color.
    `type` 0 activates the lines clockwise, 1 counter-clockwise.
    See https://www.openhasp.com/0.7.0/design/objects/linemeter/
    """

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, DISC_DEFAULTS))
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        count = max(int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT)), 1)
        angle = number(self.obj_data.get("angle"), DEFAULT_SCALE_ANGLE)
        start = scale_start(angle, number(self.obj_data.get("rotation"), 0))
        # measured on a plate: the lines of the value have the `line_width` of the indicator (10, or of the main part), the others
        # are always as wide as the default. The color of the lines of the value goes from `line_color` to `scale_grad_color`.
        active_width = number(
            self.style("line_width", _DEFAULT_LINE_WIDTH, Part.INDICATOR)
            if "line_width10" in self.obj_data
            else self.style("line_width", _DEFAULT_LINE_WIDTH),
            _DEFAULT_LINE_WIDTH,
        )
        radius = min(self.obj_w, self.obj_h) / 2 - _LINE_INSET
        center = self.obj_rect.center()
        active = active_lines(int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT)), value_fraction(self.data))
        reverse = int(number(self.obj_data.get("type"), 0)) == 1
        inactive_color = to_color(self.obj_data.get("scale_end_color"), _INACTIVE)
        active_color = to_color(self.style("line_color", self.style("line_color", _ACTIVE), Part.INDICATOR), _ACTIVE)
        grad_color = to_color(self.obj_data.get("scale_grad_color"), _ACTIVE)

        for line in range(count):
            is_active = line >= count - active if reverse else line < active
            color = mix(active_color, grad_color, line / count) if is_active else inactive_color
            pen = QtGui.QPen(color, active_width if is_active else _DEFAULT_LINE_WIDTH)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            degrees = start + angle * line / max(count - 1, 1)
            painter.drawLine(polar(center, radius, degrees), polar(center, radius - _LINE_LENGTH, degrees))
        super().paint(painter, option, widget)
