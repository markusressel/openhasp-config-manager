import math

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.interaction import DRAG_LIMIT, LONG_PRESS_TIME
from openhasp_config_manager.gui.domain.touch_values import lvgl_atan2
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import DEFAULT_RADIUS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: the ring of colors is 20 pixels wide, then comes a gray ring of 12 pixels, then the disc with the color
_DEFAULT_SCALE_WIDTH = 20
_DEFAULT_PAD_INNER = 12
_RING_COLOR = TRACK_DEFAULTS["bg_color"]
_KNOB_RADIUS = 16
_KNOB_BORDER_COLOR = "#838183"
_KNOB_BORDER_WIDTH = 2
_DEFAULT_COLOR = "#FF0000"
# `LV_DPI / 2` of lv_conf_v7.h: the inner circle of a disc is at least this big when the ring is searched
_MIN_INNER_RADIUS = 50
_MODES = ("hue", "saturation", "value")
# a double click puts the part of the color that the mode changes back to this (`LV_CPICKER_DEF_HUE`, `_SATURATION`, `_VALUE`)
_DEFAULTS = {"hue": 0, "saturation": 100, "value": 100}


class HaspColorPickerItem(EditableWidget):
    """
    A color picker: a gradient ring (a bar if the object is wider than tall) around a circle with the selected `color`. `mode`
    says what the gradient changes: `hue` (default), `saturation` or `value`; the other two stay as in `color`.
    Touched, the color follows a finger that drags on the ring (or the bar), like `lv_cpicker.c`: in the middle of the disc nothing
    changes. A finger that rests (moves no more than 5 pixels) in the middle of the disc for 400 ms, or anywhere on the bar for 800 ms,
    switches `mode` to the next one, unless `mode_fixed`. A second press within 400 ms of the first (a double click) puts the part of
    the color that the mode changes back to its default (hue 0, saturation and value 100). After either the finger changes nothing until
    it is let go. The plate sends no action for it.
    See https://www.openhasp.com/0.7.0/design/objects/cpicker/
    """

    # the finger is in the middle of the disc, where it doesn't change the color
    _inner = False
    # the time the input device told of last
    _now = 0.0
    # when the last press began (`last_click_time`), for double clicks
    _last_click = None
    # where the finger is (rounded, None if it is up) and when it last moved more than half the drag limit (`last_change_time`)
    _last_point = None
    _last_change = 0.0
    # the mode changed or the color was reset: nothing changes until the finger is let go (`lv_indev_wait_release`)
    _waiting = False

    @property
    def mode(self) -> str:
        return str(self.data.get("mode", "hue"))

    @property
    def keeps_press(self) -> bool:
        # `LV_PROTECT_PRESS_LOST`
        return True

    def hit(self, local: QtCore.QPointF) -> bool:
        if not self.obj_rect.contains(local):
            return False
        if self.obj_w > self.obj_h:
            return True
        # `lv_obj_set_adv_hittest`: only the circle is touched
        radius = min(self.obj_w, self.obj_h) / 2
        center = self.obj_rect.center()
        return (local.x() - center.x()) ** 2 + (local.y() - center.y()) ** 2 <= radius * radius

    def _on_ring(self, dx: float, dy: float) -> bool:
        side = min(self.obj_w, self.obj_h)
        scale_width = number(self.style("scale_width", _DEFAULT_SCALE_WIDTH), _DEFAULT_SCALE_WIDTH)
        inner = side // 2 - scale_width
        if inner > _MIN_INNER_RADIUS:
            inner = max(inner - number(self.style("pad_inner", _DEFAULT_PAD_INNER), _DEFAULT_PAD_INNER), _MIN_INNER_RADIUS)
        return dx * dx + dy * dy >= inner * inner

    @property
    def is_bar(self) -> bool:
        return self.obj_w > self.obj_h

    def on_time(self, now: float):
        self._now = now
        if self._last_point is not None and not self._waiting:
            # a resting finger is read as well
            self._switch_mode_after_rest()

    def on_press(self, point):
        """`LV_SIGNAL_PRESSED`"""
        self._inner = False
        self._waiting = False
        self._last_point = None
        self._last_change = self._now
        double_click = self._last_click is not None and self._now - self._last_click < LONG_PRESS_TIME
        self._last_click = self._now
        if double_click:
            self._waiting = True
            self._set_hsv(_DEFAULTS.get(self.mode, 0))
        else:
            self.on_pressing(point)

    def on_pressing(self, point):
        """`LV_SIGNAL_PRESSING`"""
        if self._waiting:
            return
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        finger = (int(local.x()), int(local.y()))
        if (
            self._last_point is None
            or max(abs(finger[0] - self._last_point[0]), abs(finger[1] - self._last_point[1])) > DRAG_LIMIT // 2
        ):
            self._last_change = self._now
            self._last_point = finger
        if self.is_bar:
            if self._switch_mode_after_rest():
                return
            angle = min(max(int(local.x() * 360 // self.obj_w), 0), 359)
        else:
            center = self.obj_rect.center()
            dx, dy = int(local.x() - center.x()), int(local.y() - center.y())
            self._inner = not self._on_ring(dx, dy)
            if self._switch_mode_after_rest() or self._inner or (dx == 0 and dy == 0):
                return
            angle = lvgl_atan2(dx, dy) % 360
        self._set_hsv(angle * 100 // 360 if self.mode in ("saturation", "value") else angle)

    def _set_hsv(self, part: int):
        """Change the part of the color that the mode changes: the hue (0 to 359), or the saturation or value (0 to 100)."""
        color = self.color
        hue, saturation, value = (
            round(max(color.hsvHueF(), 0) * 360) % 360,
            round(color.hsvSaturationF() * 100),
            round(color.valueF() * 100),
        )
        if self.mode == "saturation":
            saturation = part
        elif self.mode == "value":
            value = part
        else:
            hue = part
        changed = QtGui.QColor.fromHsv(hue, round(saturation * 255 / 100), round(value * 255 / 100)).name().upper()
        if changed != color.name().upper():
            self.runtime.set(self.key, "color", changed, self.obj_data)
            self.runtime_changed()

    def _switch_mode_after_rest(self) -> bool:
        """:return: whether the finger rested long enough (in the middle of the disc, or on the bar) to go to the next mode"""
        if number(self.data.get("mode_fixed"), 0) or not (self.is_bar or self._inner):
            return False
        if self._now - self._last_change <= (2 * LONG_PRESS_TIME if self.is_bar else LONG_PRESS_TIME):
            return False
        mode = _MODES[(_MODES.index(self.mode) + 1) % len(_MODES)] if self.mode in _MODES else _MODES[0]
        self.runtime.set(self.key, "mode", mode, self.obj_data)
        self.runtime_changed()
        self._waiting = True
        return True

    def on_release(self, point, short_click: bool):
        self._last_point = None
        super().on_release(point, short_click)

    def on_press_lost(self):
        self._last_point = None
        super().on_press_lost()

    def on_long_press(self):
        # the color picker times the rest itself
        pass

    @property
    def color(self) -> QtGui.QColor:
        return to_color(self.data.get("color"), _DEFAULT_COLOR)

    def gradient_stops(self, steps: int = 12):
        """:return: (position 0 to 1, color) along the gradient of the current mode"""
        hue, saturation, value, _ = self.color.getHsvF()
        mode = self.mode
        stops = []
        for step in range(steps + 1):
            position = step / steps
            if mode == "saturation":
                color = QtGui.QColor.fromHsvF(max(hue, 0), position, value)
            elif mode == "value":
                color = QtGui.QColor.fromHsvF(max(hue, 0), saturation, position)
            else:
                color = QtGui.QColor.fromHsvF(position * 0.999999, 1, 1)
            stops.append((position, color))
        return stops

    def position(self) -> float:
        """:return: where the selected color is on the gradient, 0 to 1"""
        hue, saturation, value, _ = self.color.getHsvF()
        mode = self.mode
        return saturation if mode == "saturation" else value if mode == "value" else max(hue, 0.0)

    def _draw_knob(self, painter, center: QtCore.QPointF):
        painter.setPen(QtGui.QPen(QtGui.QColor(_KNOB_BORDER_COLOR), _KNOB_BORDER_WIDTH))
        painter.setBrush(self.color)
        painter.drawEllipse(center, _KNOB_RADIUS, _KNOB_RADIUS)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.obj_rect
        if self.is_bar:
            gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
            for position, color in self.gradient_stops():
                gradient.setColorAt(position, color)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, DEFAULT_RADIUS, DEFAULT_RADIUS)
            # the knob is a circle on the bar, a bit bigger than the bar is high
            self._draw_knob(painter, QtCore.QPointF(rect.left() + rect.width() * self.position(), rect.center().y()))
            return super().paint(painter, option, widget)

        side = min(self.obj_w, self.obj_h)
        scale_width = number(self.style("scale_width", _DEFAULT_SCALE_WIDTH), _DEFAULT_SCALE_WIDTH)
        outer = QtCore.QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
        # the colors go counter-clockwise from 6 o'clock (Qt's conical gradient starts at 3 o'clock, counter-clockwise)
        gradient = QtGui.QConicalGradient(outer.center(), 270)
        for position, color in self.gradient_stops():
            gradient.setColorAt(min(position, 0.999999), color)
        pen = QtGui.QPen(QtGui.QBrush(gradient), scale_width)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(outer.adjusted(scale_width / 2, scale_width / 2, -scale_width / 2, -scale_width / 2))

        pad = number(self.obj_data.get("pad_inner"), _DEFAULT_PAD_INNER)
        ring = outer.adjusted(scale_width, scale_width, -scale_width, -scale_width)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(_RING_COLOR))
        painter.drawEllipse(ring)
        inner = ring.adjusted(pad, pad, -pad, -pad)
        painter.setBrush(self.color)
        painter.drawEllipse(inner)

        self._draw_knob(painter, self.knob_center())
        super().paint(painter, option, widget)

    def knob_center(self) -> QtCore.QPointF:
        """
        :return: where the knob of a disc is: in the middle of the ring of colors, at the selected color. Like `lv_cpicker.c`
            (`x = r * sin(angle)`, `y = r * cos(angle)`): 0 degrees at 6 o'clock, 90 at 3 o'clock, the way a touch is read.
        """
        side = min(self.obj_w, self.obj_h)
        scale_width = number(self.style("scale_width", _DEFAULT_SCALE_WIDTH), _DEFAULT_SCALE_WIDTH)
        angle = math.radians(360 * self.position())
        middle = (side - scale_width) / 2
        center = self.obj_rect.center()
        return QtCore.QPointF(center.x() + math.sin(angle) * middle, center.y() + math.cos(angle) * middle)
