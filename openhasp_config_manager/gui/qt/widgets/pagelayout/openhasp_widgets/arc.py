import dataclasses
import math
import time

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.touch_values import ArcDrag, arc_last_angle, arc_value
from openhasp_config_manager.gui.domain.interaction import is_true
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    CIRCLE_RADIUS,
    DISC_DEFAULTS,
    KNOB_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    centered_square,
    draw_text,
    number,
    plate_font,
    round_pen,
    to_color,
    value_fraction,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# LVGL draws the background arc from 135 to 45 degrees (clockwise from 3 o'clock) if the object says nothing else
_DEFAULT_START = 135
_DEFAULT_END = 45
_DEFAULT_LINE_WIDTH = 15.5
_DEFAULT_KNOB_RADIUS = 8
# measured on a plate: what is behind the arcs, the arc of the track and the arc of the indicator
_PLATE_DEFAULTS = {"bg_color": "#505A60", "bg_opa": 255, "radius": CIRCLE_RADIUS}
_TRACK_COLOR = "#6A6D7B"
_INDICATOR_COLOR = "#00B6FF"
# the disc inside of the arcs
_DISC_DEFAULTS = {**DISC_DEFAULTS, "border_width": 0}


# the arc reacts to a finger this far outside of it as well (`lv_obj_set_ext_click_area(arc, LV_DPI / 10, ...)`)
_CLICK_REACH = 10


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
        part = value_fraction(self.data) * sweep
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
        knob_radius = _DEFAULT_KNOB_RADIUS if self.adjustable else 0
        full = centered_square(self.obj_w, self.obj_h)
        inset = max(track_width, indicator_width) / 2 + knob_radius
        rect = full.adjusted(inset, inset, -inset, -inset)
        (start, sweep), (ind_start, ind_sweep) = self.angles()

        # the plate behind the arcs, and the disc inside of them (the main part: `bg_color`, `border_width`, ...)
        draw_box(painter, full, box_style(self, Part.MAIN, _PLATE_DEFAULTS))
        # measured on a plate: the disc is as far from the edge as the default arc is wide, whatever the width of the arcs is
        width = _DEFAULT_LINE_WIDTH
        disc = dataclasses.replace(box_style(self, Part.MAIN, _DISC_DEFAULTS), border_width=0, outline_width=0, shadow_width=0)
        draw_box(painter, full.adjusted(width, width, -width, -width), disc)

        def arc(color, width, first, span):
            painter.setPen(round_pen(color, width))
            painter.drawArc(rect, int(-first * 16), int(-span * 16))

        arc(to_color(self.style("line_color", _TRACK_COLOR), _TRACK_COLOR), track_width, start, sweep)
        if ind_sweep > 0:
            arc(
                to_color(self.style("line_color", _INDICATOR_COLOR, Part.INDICATOR), _INDICATOR_COLOR),
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
            draw_box(
                painter,
                QtCore.QRectF(point.x() - knob_radius, point.y() - knob_radius, knob_radius * 2, knob_radius * 2),
                box_style(self, Part.KNOB, {**KNOB_DEFAULTS, "radius": CIRCLE_RADIUS}),
            )

        text = self.obj_data.get("value_str")
        if text:
            draw_text(
                painter,
                self.obj_rect,
                str(text),
                to_color(self.obj_data.get("value_color"), DEFAULT_TEXT),
                plate_font(self.obj_data.get("value_font", DEFAULT_FONT_SIZE)),
            )
        super().paint(painter, option, widget)

    # --- touches ---

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data, parent_widget)
        self._drag = ArcDrag()

    @property
    def adjustable(self) -> bool:
        return is_true(self.data.get("adjustable"), False)

    @property
    def keeps_press(self) -> bool:
        # `lv_obj_add_protect(arc, LV_PROTECT_PRESS_LOST)`
        return True

    def hit(self, local: QtCore.QPointF) -> bool:
        return self.obj_rect.adjusted(-_CLICK_REACH, -_CLICK_REACH, _CLICK_REACH, _CLICK_REACH).contains(local)

    def on_press(self, point):
        self._drag = ArcDrag()
        super().on_press(point)

    def on_pressing(self, point):
        """`LV_SIGNAL_PRESSING` of an adjustable arc: turn the arc to the finger, as fast as LVGL lets it."""
        if not self.adjustable:
            return
        data = self.data
        minimum, maximum = int(number(data.get("min"), 0)), int(number(data.get("max"), 100))
        if minimum == maximum:
            return
        start = int(number(self.style("start_angle", _DEFAULT_START), _DEFAULT_START))
        end = int(number(self.style("end_angle", _DEFAULT_END), _DEFAULT_END))
        rotation = int(number(data.get("rotation"), 0))
        kind = int(number(data.get("type"), 0))
        current = int(max(minimum, min(number(data.get("val"), minimum), maximum)))
        full = centered_square(self.obj_w, self.obj_h)
        center = full.center()
        track_width = number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH)
        indicator_width = number(self.style("line_width", track_width, Part.INDICATOR), track_width)
        value = arc_value(
            self._drag,
            dx=int(point[0]) - int(self.pos().x() + center.x()),
            dy=int(point[1]) - int(self.pos().y() + center.y()),
            radius=int(full.width() / 2),
            indicator_width=int(indicator_width),
            background_start=start,
            background_end=end,
            rotation=rotation,
            minimum=minimum,
            maximum=maximum,
            current_value=current,
            last_angle=arc_last_angle(kind, current, minimum, maximum, start, end),
            now=time.monotonic(),
        )
        if value is not None and value != current:
            self.runtime.set(self.key, "val", value, self.obj_data)
            self.runtime_changed()

    def on_release(self, point, short_click: bool):
        self._drag = ArcDrag()
        if self.adjustable:
            self.set_pressed(False)
            self._follow_group()
        else:
            super().on_release(point, short_click)

    def on_press_lost(self):
        self._drag = ArcDrag()
        super().on_press_lost()

    def on_long_press(self):
        if self.adjustable:
            self._follow_group()
        else:
            super().on_long_press()

    def on_long_press_repeat(self):
        if self.adjustable:
            self._follow_group()
        else:
            super().on_long_press_repeat()

    def _touch_event(self, event: str):
        # an adjustable arc is handled by `slider_event_handler`: no action
        if not self.adjustable:
            super()._touch_event(event)

    def _follow_group(self):
        if self.parent_widget is not None:
            data = self.data
            minimum, maximum = int(number(data.get("min"), 0)), int(number(data.get("max"), 100))
            value = int(number(data.get("val"), minimum))
            self.parent_widget.follow_group(self, power=bool(value), value=value, minimum=minimum, maximum=maximum)
