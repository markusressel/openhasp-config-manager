from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, capped_radius, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INDICATOR_DEFAULTS,
    KNOB_DEFAULTS,
    SWITCH_KNOB_PADDING,
    TRACK_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspSwitchItem(EditableWidget):
    @property
    def keeps_press(self) -> bool:
        # `lv_obj_add_protect(sw, LV_PROTECT_PRESS_LOST)`: it switches when the finger is released anywhere
        return True

    def on_release(self, point, short_click: bool):
        """`lv_switch_signal`: the switch changes on release, and `toggle_event_handler` lets the group follow."""
        self.set_pressed(False)
        self.toggle()

    def _touch_event(self, event: str):
        # the toggle handler only reports: no action
        pass

    def _knob_rect(self, inner: QtCore.QRectF) -> QtCore.QRectF:
        """
        The knob is as high as the switch and about as wide, plus its padding. It sits at the left end of the track, or at the right
        end while on: the padding of the track moves its ends, the padding of the knob makes the knob bigger.
        """
        left, top, right, bottom = padding(self, Part.KNOB, SWITCH_KNOB_PADDING)
        width = self.obj_h + 1 + left + right
        height = self.obj_h + top + bottom
        if self.is_toggled:
            x = inner.right() + right + 1 - width
        else:
            x = inner.left() - left
        return QtCore.QRectF(x, -top, width, height)

    def paint(self, painter, option, widget=None):
        track = self.obj_rect
        track_style = box_style(self, Part.MAIN, TRACK_DEFAULTS)
        draw_box(painter, track, track_style)

        left, top, right, bottom = padding(self, Part.MAIN)
        inner = track.adjusted(left, top, -right, -bottom)
        knob = self._knob_rect(inner)

        if self.is_toggled:
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
