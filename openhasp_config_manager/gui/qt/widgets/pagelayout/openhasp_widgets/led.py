from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_COLOR = "#2196F3"
# like LVGL, an LED with brightness 0 is still visible, only dim
_MIN_BRIGHTNESS = 80


class HaspLedItem(EditableWidget):
    """
    A round light. `val` is the brightness (0 to 255), the color comes from `bg_color`. A bright LED glows.
    See https://www.openhasp.com/0.7.0/design/objects/led/
    """

    @property
    def brightness(self) -> float:
        """:return: how bright the LED is drawn, 0 (dim) to 1"""
        val = max(0.0, min(number(self.obj_data.get("val"), 0), 255.0))
        return val / 255

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        color = to_color(self.style("bg_color"), _DEFAULT_COLOR)
        scale = (_MIN_BRIGHTNESS + (255 - _MIN_BRIGHTNESS) * self.brightness) / 255
        body = QtGui.QColor.fromRgbF(color.redF() * scale, color.greenF() * scale, color.blueF() * scale)
        rect = self.obj_rect
        painter.setPen(QtGui.QPen(body.lighter(130), 2))
        painter.setBrush(body)
        painter.drawEllipse(rect)
        if self.brightness > 0:
            glow = QtGui.QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 2)
            glow.setColorAt(0, QtGui.QColor(255, 255, 255, int(110 * self.brightness)))
            glow.setColorAt(1, QtCore.Qt.GlobalColor.transparent)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(rect)
        super().paint(painter, option, widget)
