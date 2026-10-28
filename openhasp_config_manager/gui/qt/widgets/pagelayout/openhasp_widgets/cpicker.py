import math

from PyQt6 import QtCore, QtGui

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


class HaspColorPickerItem(EditableWidget):
    """
    A color picker: a gradient ring (a bar if the object is wider than tall) around a circle with the selected `color`. `mode`
    says what the gradient changes: `hue` (default), `saturation` or `value`; the other two stay as in `color`.
    See https://www.openhasp.com/0.7.0/design/objects/cpicker/
    """

    @property
    def color(self) -> QtGui.QColor:
        return to_color(self.obj_data.get("color"), _DEFAULT_COLOR)

    def gradient_stops(self, steps: int = 12):
        """:return: (position 0 to 1, color) along the gradient of the current mode"""
        hue, saturation, value, _ = self.color.getHsvF()
        mode = str(self.obj_data.get("mode", "hue"))
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
        mode = str(self.obj_data.get("mode", "hue"))
        return saturation if mode == "saturation" else value if mode == "value" else max(hue, 0.0)

    def _draw_knob(self, painter, center: QtCore.QPointF):
        painter.setPen(QtGui.QPen(QtGui.QColor(_KNOB_BORDER_COLOR), _KNOB_BORDER_WIDTH))
        painter.setBrush(self.color)
        painter.drawEllipse(center, _KNOB_RADIUS, _KNOB_RADIUS)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.obj_rect
        if self.obj_w > self.obj_h:
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

        # the knob sits in the middle of the ring of colors, where the selected color is
        angle = math.radians(90 + 360 * self.position())
        middle = (side - scale_width) / 2
        self._draw_knob(
            painter,
            QtCore.QPointF(outer.center().x() + math.cos(angle) * middle, outer.center().y() + math.sin(angle) * middle),
        )
        super().paint(painter, option, widget)
