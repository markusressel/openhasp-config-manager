from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.bar_values import SLIDER_RANGE, bar_range, pressed_knob, slider_type
from openhasp_config_manager.gui.domain.meter_geometry import fraction
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.touch_values import slider_value
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    KNOB_DEFAULTS,
    SLIDER_KNOB_PADDING,
    TRACK_DEFAULTS,
    TRACK_PADDING,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import SELECTION_MARGIN


# the slider reacts to a finger this far above and below it as well (`lv_obj_set_ext_click_area(slider, 0, 0, LV_DPI / 10, LV_DPI / 10)`)
_CLICK_REACH = 10


class HaspSliderItem(HaspBarItem):
    """
    A bar with a knob (part 2) at the end of the indicator: a square as big as the slider is thick, plus its padding. `type` 1
    (symmetrical) fills from 0, `type` 2 (range) has a second knob at `start_value`. A finger drags the knob it pressed (in range
    mode the one nearer to it); `val` can't go below `start_value`, `start_value` not above `val`.
    """

    is_slider = True

    def __init__(self, *args, **kwargs):
        # the knob the finger moves (`value_to_set`): "val" or "start"
        self._knob = "val"
        super().__init__(*args, **kwargs)

    @property
    def min_val(self) -> int:
        return self.data.get("min", 0)

    @property
    def max_val(self) -> int:
        return self.data.get("max", 100)

    @property
    def val(self) -> int:
        return self.data.get("val", 0)

    @property
    def progress(self) -> float:
        return fraction(self.val, self.min_val, self.max_val)

    @property
    def is_range(self) -> bool:
        return slider_type(self.data) == SLIDER_RANGE

    def _knob_rect(self, progress=None) -> QtCore.QRectF:
        """:param progress: where the knob is (0 to 1), by default at `val`"""
        progress = self.progress if progress is None else progress
        inner = self.inner_rect()
        left, top, right, bottom = padding(self, Part.KNOB, SLIDER_KNOB_PADDING)
        thickness = min(self.obj_w, self.obj_h)
        width, height = thickness + left + right, thickness + top + bottom
        if self.is_vertical:
            center = QtCore.QPointF(self.obj_w / 2, inner.bottom() - inner.height() * progress)
        else:
            center = QtCore.QPointF(inner.left() + inner.width() * progress, self.obj_h / 2)
        return QtCore.QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def _start_knob_rect(self) -> QtCore.QRectF:
        minimum, maximum, start, _ = bar_range(self.data, slider=True)
        return self._knob_rect(fraction(start, minimum, maximum))

    def boundingRect(self) -> QtCore.QRectF:
        """The knobs reach over the track."""
        knobs = self._knob_rect().united(self._start_knob_rect())
        return (
            super()
            .boundingRect()
            .united(knobs.adjusted(-SELECTION_MARGIN, -SELECTION_MARGIN, SELECTION_MARGIN, SELECTION_MARGIN))
        )

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        self.draw_indicator(painter)

        draw_box(painter, self._knob_rect(), box_style(self, Part.KNOB, KNOB_DEFAULTS))
        if self.is_range:
            draw_box(painter, self._start_knob_rect(), box_style(self, Part.KNOB, KNOB_DEFAULTS))

        # selection outline of the base class
        super(HaspBarItem, self).paint(painter, option, widget)

    # --- touches ---

    @property
    def keeps_press(self) -> bool:
        # `lv_obj_add_protect(slider, LV_PROTECT_PRESS_LOST)`: the knob follows the finger also outside of the slider
        return True

    def hit(self, local: QtCore.QPointF) -> bool:
        return self.obj_rect.adjusted(0, -_CLICK_REACH, 0, _CLICK_REACH).contains(local)

    def on_press(self, point):
        """`LV_SIGNAL_PRESSED`: in range mode the finger takes the knob nearer to it."""
        super().on_press(point)
        self._knob = "val"
        if self.is_range:
            local = self.mapFromScene(QtCore.QPointF(int(point[0]), int(point[1])))
            right, left = self._knob_rect(), self._start_knob_rect()
            if self.is_vertical:
                self._knob = pressed_knob(local.y(), (left.top(), left.bottom()), (right.top(), right.bottom()), vertical=True)
            else:
                self._knob = pressed_knob(
                    local.x(), (left.left(), left.right()), (right.left(), right.right()), vertical=False
                )

    def on_pressing(self, point):
        """`LV_SIGNAL_PRESSING`: the value of the knob is where the finger is on the track, but not beyond the other one."""
        local = self.mapFromScene(QtCore.QPointF(int(point[0]), int(point[1])))
        left, top, right, bottom = padding(self, Part.MAIN, TRACK_PADDING)
        minimum, maximum, start, current = bar_range(self.data, slider=True)
        if self.is_vertical:
            value = slider_value(int(local.y()), self.obj_h, top, bottom, minimum, maximum, vertical=True)
        else:
            value = slider_value(int(local.x()), self.obj_w, left, right, minimum, maximum, vertical=False)
        if self._knob == "start":
            key, value, before = "start_value", min(value, current), start
        else:
            key, value, before = "val", max(value, start), current
        if value != before:
            self.runtime.set(self.key, key, value, self.obj_data)
            self.runtime_changed()

    def on_release(self, point, short_click: bool):
        self.set_pressed(False)
        self._follow_group()

    def on_long_press(self):
        self._follow_group()

    def on_long_press_repeat(self):
        self._follow_group()

    def _touch_event(self, event: str):
        # `slider_event_handler` sends the value, there is no action
        pass

    def _follow_group(self):
        """The objects in the group take the value on release, and while the finger rests on the slider (`changed`)."""
        if self.parent_widget is not None:
            minimum, maximum = int(number(self.min_val, 0)), int(number(self.max_val, 100))
            value = int(number(self.val, 0))
            self.parent_widget.follow_group(self, power=bool(value), value=value, minimum=minimum, maximum=maximum)
