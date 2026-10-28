from typing import List

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    draw_text,
    fraction,
    number,
    plate_font,
    polar,
    scale_start,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ANGLE = 240
_DEFAULT_LINE_COUNT = 31
_DEFAULT_LABEL_COUNT = 6
_DEFAULT_CRITICAL_VALUE = 80
# measured on a plate: the scale is gray and its critical part blue, the labels and the needle are white
_SCALE_COLOR = "#8B898B"
_CRITICAL_COLOR = "#00B6FF"
_NEEDLE_COLOR = "#EEEEEE"
_MINOR_COLOR = "#5A6070"
_DEFAULT_FONT = 24
# the disc behind the dial: a round track, there is no border by default
_DISC_DEFAULTS = {**TRACK_DEFAULTS, "radius": 1000}


class HaspGaugeItem(EditableWidget):
    """
    A dial: `line_count` minor ticks and `label_count` major ticks with labels around `angle` degrees (rotated by `rotation`), and
    a needle that points at `val`. Ticks after `critical_value` are drawn in the `scale_end_color`. `format` divides the labels by
    10, 100, ... (1 to 4).
    See https://www.openhasp.com/0.7.0/design/objects/gauge/
    """

    def labels(self) -> List[str]:
        """:return: the texts of the major ticks, from the smallest to the largest value"""
        count = max(int(number(self.obj_data.get("label_count"), _DEFAULT_LABEL_COUNT)), 0)
        low, high = number(self.obj_data.get("min"), 0), number(self.obj_data.get("max"), 100)
        divider = 10 ** int(number(self.obj_data.get("format"), 0))
        return [str(int((low + (high - low) * index / max(count - 1, 1)) / divider)) for index in range(count)]

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DISC_DEFAULTS))
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        angle = number(self.obj_data.get("angle"), _DEFAULT_ANGLE)
        start = scale_start(angle, number(self.obj_data.get("rotation"), 0))
        radius = min(self.obj_w, self.obj_h) / 2 - 2
        center = self.obj_rect.center()
        minimum, maximum = self.obj_data.get("min", 0), self.obj_data.get("max", 100)
        critical = fraction(self.obj_data.get("critical_value", _DEFAULT_CRITICAL_VALUE), minimum, maximum)
        scale_color = to_color(self.style("line_color"), _SCALE_COLOR)
        critical_color = to_color(self.style("scale_end_color"), _CRITICAL_COLOR)
        # on the plate the minor ticks hardly show on the default disc
        minor_color = to_color(self.style("line_color"), _MINOR_COLOR)

        count = max(int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT)), 2)
        for tick in range(count):
            position = tick / (count - 1)
            painter.setPen(QtGui.QPen(critical_color if position > critical else minor_color, 1.5))
            degrees = start + angle * position
            painter.drawLine(polar(center, radius, degrees), polar(center, radius * 0.88, degrees))

        labels = self.labels()
        for index, label in enumerate(labels):
            position = index / max(len(labels) - 1, 1)
            degrees = start + angle * position
            painter.setPen(QtGui.QPen(critical_color if position > critical else scale_color, 5))
            painter.drawLine(polar(center, radius, degrees), polar(center, radius * 0.76, degrees))
            spot = polar(center, radius * 0.5, degrees)
            draw_text(
                painter,
                QtCore.QRectF(spot.x() - 30, spot.y() - 12, 60, 24),
                label,
                to_color(self.style("text_color"), _NEEDLE_COLOR),
                plate_font(self.style("text_font", _DEFAULT_FONT)),
            )

        needle = polar(center, radius * 0.7, start + angle * fraction(self.obj_data.get("val", 0), minimum, maximum))
        pen = QtGui.QPen(to_color(self.style("line_color", _NEEDLE_COLOR, Part.INDICATOR), _NEEDLE_COLOR), 5)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(center, needle)
        painter.setBrush(QtGui.QColor(_NEEDLE_COLOR))
        painter.drawEllipse(center, 8, 8)
        super().paint(painter, option, widget)
