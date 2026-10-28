from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, capped_radius, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INDICATOR_DEFAULTS,
    KNOB_DEFAULTS,
    SWITCH_KNOB_PADDING,
    TRACK_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# how long the knob takes to move when the switch is touched (`anim_time`, the default of `lv_bar_create`), linear
DEFAULT_ANIM_TIME = 200


class HaspSwitchItem(EditableWidget):
    def __init__(self, *args, **kwargs):
        # while the knob moves after a touch: how far it is, 0 (off) to 1 (on)
        self._anim = None
        super().__init__(*args, **kwargs)

    @property
    def keeps_press(self) -> bool:
        # `lv_obj_add_protect(sw, LV_PROTECT_PRESS_LOST)`: it switches when the finger is released anywhere
        return True

    def on_release(self, point, short_click: bool):
        """`lv_switch_signal`: the switch changes on release, and `toggle_event_handler` lets the group follow."""
        self.set_pressed(False)
        self.toggle()
        # `lv_switch_on`/`lv_switch_off` with `LV_ANIM_ON`: the value of the bar moves to the other end in `anim_time`
        self.finish_animation()
        duration = int(number(self.data.get("anim_time"), DEFAULT_ANIM_TIME))
        if duration > 0:
            animation = QtCore.QVariantAnimation(self)
            animation.setStartValue(0.0 if self.is_toggled else 1.0)
            animation.setEndValue(1.0 if self.is_toggled else 0.0)
            animation.setDuration(duration)
            animation.valueChanged.connect(lambda _value: self.update())
            animation.finished.connect(self.finish_animation)
            self._anim = animation
            animation.start()

    def finish_animation(self):
        """Let the knob arrive at once (also when tests don't wait for time)."""
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
            self.update()

    @property
    def position(self) -> float:
        """Where the knob is: 0 at the off end, 1 at the on end, in between while it moves."""
        if self._anim is not None:
            return float(self._anim.currentValue())
        return 1.0 if self.is_toggled else 0.0

    def _touch_event(self, event: str):
        # the toggle handler only reports: no action
        pass

    def _knob_rect(self, inner: QtCore.QRectF) -> QtCore.QRectF:
        """
        The knob is as high as the switch and about as wide, plus its padding. It sits at the left end of the track, or at the right
        end while on (in between while it moves, see `position`): the padding of the track moves its ends, the padding of the knob makes
        the knob bigger.
        """
        left, top, right, bottom = padding(self, Part.KNOB, SWITCH_KNOB_PADDING)
        width = self.obj_h + 1 + left + right
        height = self.obj_h + top + bottom
        off, on = inner.left() - left, inner.right() + right + 1 - width
        return QtCore.QRectF(off + (on - off) * self.position, -top, width, height)

    def paint(self, painter, option, widget=None):
        track = self.obj_rect
        track_style = box_style(self, Part.MAIN, TRACK_DEFAULTS)
        draw_box(painter, track, track_style)

        left, top, right, bottom = padding(self, Part.MAIN)
        inner = track.adjusted(left, top, -right, -bottom)
        knob = self._knob_rect(inner)

        if self.position > 0:
            # the indicator fills the track up to the middle of the knob, and the shape of the track cuts it
            indicator = QtCore.QRectF(inner.left(), inner.top(), knob.center().x() - inner.left(), inner.height())
            painter.save()
            shape = QtGui.QPainterPath()
            radius = capped_radius(track, track_style.radius)
            shape.addRoundedRect(track, radius, radius)
            painter.setClipPath(shape)
            draw_box(painter, indicator, box_style(self, Part.INDICATOR, INDICATOR_DEFAULTS))
            painter.restore()

        draw_box(painter, knob, box_style(self, Part.KNOB, KNOB_DEFAULTS))

        super().paint(painter, option, widget)

    def boundingRect(self) -> QtCore.QRectF:
        # the knob reaches over the track
        reach = max(padding(self, Part.KNOB, SWITCH_KNOB_PADDING)) + 1
        return super().boundingRect().adjusted(-reach, -reach, reach, reach)
