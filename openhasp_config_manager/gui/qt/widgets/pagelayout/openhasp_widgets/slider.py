from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.touch_values import slider_value
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem, indicator_rect
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INDICATOR_DEFAULTS,
    KNOB_DEFAULTS,
    SLIDER_KNOB_PADDING,
    TRACK_DEFAULTS,
    TRACK_PADDING,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import fraction, number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import SELECTION_MARGIN


# the slider reacts to a finger this far above and below it as well (`lv_obj_set_ext_click_area(slider, 0, 0, LV_DPI / 10, LV_DPI / 10)`)
_CLICK_REACH = 10


class HaspSliderItem(HaspBarItem):
    """A bar with a knob (part 2) at the end of the indicator: a square as big as the slider is thick, plus its padding."""

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

    def _knob_rect(self) -> QtCore.QRectF:
        inner = self.inner_rect()
        left, top, right, bottom = padding(self, Part.KNOB, SLIDER_KNOB_PADDING)
        thickness = min(self.obj_w, self.obj_h)
        width, height = thickness + left + right, thickness + top + bottom
        if self.is_vertical:
            center = QtCore.QPointF(self.obj_w / 2, inner.bottom() - inner.height() * self.progress)
        else:
            center = QtCore.QPointF(inner.left() + inner.width() * self.progress, self.obj_h / 2)
        return QtCore.QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def boundingRect(self) -> QtCore.QRectF:
        """The knob reaches over the track."""
        return (
            super()
            .boundingRect()
            .united(self._knob_rect().adjusted(-SELECTION_MARGIN, -SELECTION_MARGIN, SELECTION_MARGIN, SELECTION_MARGIN))
        )

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        if self.progress > 0:
            draw_box(
                painter,
                indicator_rect(self.inner_rect(), self.progress, self.is_vertical),
                box_style(self, Part.INDICATOR, INDICATOR_DEFAULTS),
            )

        draw_box(painter, self._knob_rect(), box_style(self, Part.KNOB, KNOB_DEFAULTS))

        # selection outline of the base class
        super(HaspBarItem, self).paint(painter, option, widget)

    # --- touches ---

    @property
    def keeps_press(self) -> bool:
        # `lv_obj_add_protect(slider, LV_PROTECT_PRESS_LOST)`: the knob follows the finger also outside of the slider
        return True

    def hit(self, local: QtCore.QPointF) -> bool:
        return self.obj_rect.adjusted(0, -_CLICK_REACH, 0, _CLICK_REACH).contains(local)

    def on_pressing(self, point):
        """`LV_SIGNAL_PRESSING`: the value is where the finger is on the track."""
        local = self.mapFromScene(QtCore.QPointF(int(point[0]), int(point[1])))
        left, top, right, bottom = padding(self, Part.MAIN, TRACK_PADDING)
        minimum, maximum = int(number(self.min_val, 0)), int(number(self.max_val, 100))
        if self.is_vertical:
            value = slider_value(int(local.y()), self.obj_h, top, bottom, minimum, maximum, vertical=True)
        else:
            value = slider_value(int(local.x()), self.obj_w, left, right, minimum, maximum, vertical=False)
        if value != self.val:
            self.runtime.set(self.key, "val", value, self.obj_data)
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
