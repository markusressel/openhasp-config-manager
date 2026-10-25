import math

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_KNOB,
    DEFAULT_TRACK,
    DEFAULT_TEXT,
    draw_text,
    fraction,
    number,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# LVGL draws the background arc from 135 to 45 degrees (clockwise from 3 o'clock) if the object says nothing else
_DEFAULT_START = 135
_DEFAULT_END = 45
_DEFAULT_LINE_WIDTH = 12
_DEFAULT_KNOB_RADIUS = 8


class HaspArcItem(EditableWidget):
    """
    A ring segment from `start_angle` to `end_angle` (clockwise, 0 is at 3 o'clock, plus `rotation`) whose indicator follows `val`.
    `type` 0 fills from the start, 1 from the middle (symmetrical), 2 from the end (reverse). With `adjustable` it has a knob.
    See https://www.openhasp.com/0.7.0/design/objects/arc/
    """

    def angles(self):
        """:return: (start, sweep) of the background arc and (start, sweep) of the indicator, in degrees clockwise from 3 o'clock"""
        rotation = number(self.obj_data.get("rotation"), 0)
        start = number(self.style("start_angle", _DEFAULT_START), _DEFAULT_START) + rotation
        end = number(self.style("end_angle", _DEFAULT_END), _DEFAULT_END) + rotation
        sweep = (end - start) % 360 or 360
        part = fraction(self.obj_data.get("val", 0), self.obj_data.get("min", 0), self.obj_data.get("max", 100)) * sweep
        kind = int(number(self.obj_data.get("type"), 0))
        if kind == 1:
            if part < sweep / 2:
                indicator = (start + part, sweep / 2 - part)
            else:
                indicator = (start + sweep / 2, part - sweep / 2)
        elif kind == 2:
            indicator = (start + part, sweep - part)
        else:
            indicator = (start, part)
        return (start, sweep), indicator

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        track_width = number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH)
        indicator_width = number(self.style("line_width", track_width, Part.INDICATOR), track_width)
        knob_radius = _DEFAULT_KNOB_RADIUS if self.obj_data.get("adjustable") else 0
        side = min(self.obj_w, self.obj_h)
        inset = max(track_width, indicator_width) / 2 + knob_radius
        rect = QtCore.QRectF((self.obj_w - side) / 2, (self.obj_h - side) / 2, side, side).adjusted(
            inset, inset, -inset, -inset
        )
        (start, sweep), (ind_start, ind_sweep) = self.angles()

        def arc(color, width, first, span):
            pen = QtGui.QPen(color, width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, int(-first * 16), int(-span * 16))

        arc(to_color(self.style("line_color", DEFAULT_TRACK), DEFAULT_TRACK), track_width, start, sweep)
        if ind_sweep > 0:
            arc(
                to_color(self.style("line_color", DEFAULT_ACCENT, Part.INDICATOR), DEFAULT_ACCENT),
                indicator_width,
                ind_start,
                ind_sweep,
            )

        if knob_radius:
            angle = math.radians(ind_start + ind_sweep if self.obj_data.get("type") != 2 else ind_start)
            center = rect.center()
            point = QtCore.QPointF(
                center.x() + math.cos(angle) * rect.width() / 2, center.y() + math.sin(angle) * rect.height() / 2
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(to_color(self.style("bg_color", DEFAULT_KNOB, Part.KNOB), DEFAULT_KNOB))
            painter.drawEllipse(point, knob_radius, knob_radius)

        text = self.obj_data.get("value_str")
        if text:
            draw_text(
                painter,
                self.obj_rect,
                str(text),
                to_color(self.obj_data.get("value_color"), DEFAULT_TEXT),
                plate_font(self.obj_data.get("value_font", 25)),
            )
        super().paint(painter, option, widget)
