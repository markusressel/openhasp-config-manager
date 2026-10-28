from typing import List

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import DISC_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_SCALE_ANGLE,
    draw_text,
    fraction,
    number,
    plate_font,
    polar,
    round_pen,
    scale_start,
    to_color,
    value_fraction,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_LINE_COUNT = 31
_DEFAULT_LABEL_COUNT = 6
_DEFAULT_CRITICAL_VALUE = 80
# measured on a plate: the scale is gray and its critical part blue, the labels and the needle are white
_SCALE_COLOR = "#8B898B"
_CRITICAL_COLOR = "#00B6FF"
_NEEDLE_COLOR = "#EEEEEE"
_MINOR_COLOR = "#5A6070"
# the ticks and the needle, as a part of the radius of the dial (the minor ticks start at the edge, the major ticks are longer)
_MINOR_TICK_END = 0.88
_MAJOR_TICK_END = 0.76
_LABEL_DISTANCE = 0.5
_NEEDLE_LENGTH = 0.7
_RADIUS_INSET = 2
_MINOR_TICK_WIDTH = 1.5
_MAJOR_TICK_WIDTH = 5
_NEEDLE_WIDTH = 5
_NEEDLE_HUB_RADIUS = 8
_LABEL_SIZE = (60, 24)


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
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, DISC_DEFAULTS))
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        angle = number(self.obj_data.get("angle"), DEFAULT_SCALE_ANGLE)
        start = scale_start(angle, number(self.obj_data.get("rotation"), 0))
        radius = min(self.obj_w, self.obj_h) / 2 - _RADIUS_INSET
        center = self.obj_rect.center()
        critical = fraction(
            self.obj_data.get("critical_value", _DEFAULT_CRITICAL_VALUE),
            self.obj_data.get("min", 0),
            self.obj_data.get("max", 100),
        )
        scale_color = to_color(self.style("line_color"), _SCALE_COLOR)
        critical_color = to_color(self.style("scale_end_color"), _CRITICAL_COLOR)
        # on the plate the minor ticks hardly show on the default disc
        minor_color = to_color(self.style("line_color"), _MINOR_COLOR)

        count = max(int(number(self.obj_data.get("line_count"), _DEFAULT_LINE_COUNT)), 2)
        for tick in range(count):
            position = tick / (count - 1)
            painter.setPen(QtGui.QPen(critical_color if position > critical else minor_color, _MINOR_TICK_WIDTH))
            degrees = start + angle * position
            painter.drawLine(polar(center, radius, degrees), polar(center, radius * _MINOR_TICK_END, degrees))

        labels = self.labels()
        for index, label in enumerate(labels):
            position = index / max(len(labels) - 1, 1)
            degrees = start + angle * position
            painter.setPen(QtGui.QPen(critical_color if position > critical else scale_color, _MAJOR_TICK_WIDTH))
            painter.drawLine(polar(center, radius, degrees), polar(center, radius * _MAJOR_TICK_END, degrees))
            spot = polar(center, radius * _LABEL_DISTANCE, degrees)
            draw_text(
                painter,
                QtCore.QRectF(spot.x() - _LABEL_SIZE[0] / 2, spot.y() - _LABEL_SIZE[1] / 2, *_LABEL_SIZE),
                label,
                to_color(self.style("text_color"), _NEEDLE_COLOR),
                plate_font(self.style("text_font", DEFAULT_FONT_SIZE)),
            )

        needle = polar(center, radius * _NEEDLE_LENGTH, start + angle * value_fraction(self.data))
        painter.setPen(
            round_pen(to_color(self.style("line_color", _NEEDLE_COLOR, Part.INDICATOR), _NEEDLE_COLOR), _NEEDLE_WIDTH)
        )
        painter.drawLine(center, needle)
        painter.setBrush(QtGui.QColor(_NEEDLE_COLOR))
        painter.drawEllipse(center, _NEEDLE_HUB_RADIUS, _NEEDLE_HUB_RADIUS)
        super().paint(painter, option, widget)
