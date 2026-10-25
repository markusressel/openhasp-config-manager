from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_SCALE_WIDTH = 25
_DEFAULT_PAD_INNER = 10
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

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.obj_rect
        if self.obj_w > self.obj_h:
            gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
            for position, color in self.gradient_stops():
                gradient.setColorAt(position, color)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, 4, 4)
            return super().paint(painter, option, widget)

        side = min(self.obj_w, self.obj_h)
        scale_width = number(self.style("scale_width", _DEFAULT_SCALE_WIDTH), _DEFAULT_SCALE_WIDTH)
        outer = QtCore.QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
        gradient = QtGui.QConicalGradient(outer.center(), 90)
        for position, color in self.gradient_stops():
            gradient.setColorAt(1 - position, color)
        pen = QtGui.QPen(QtGui.QBrush(gradient), scale_width)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(outer.adjusted(scale_width / 2, scale_width / 2, -scale_width / 2, -scale_width / 2))

        pad = number(self.obj_data.get("pad_inner"), _DEFAULT_PAD_INNER)
        inner = outer.adjusted(scale_width + pad, scale_width + pad, -(scale_width + pad), -(scale_width + pad))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        painter.drawEllipse(inner)
        super().paint(painter, option, widget)
