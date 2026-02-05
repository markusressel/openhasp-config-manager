from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QGraphicsObject


class HaspSwitchItem(QGraphicsObject):
    toggled = QtCore.pyqtSignal(int, bool)

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.obj_id = obj_data.get("id", 0)
        self.val = bool(obj_data.get("val", 0))

        self.w = obj_data.get("w", 80)
        self.h = obj_data.get("h", 40)
        self.setPos(obj_data.get("x", 0), obj_data.get("y", 0))

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Track color based on state
        color = self.obj_data.get("bg_color", "#558B2F") if self.val else "#313131"
        painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.boundingRect(), self.h / 2, self.h / 2)

        # Knob
        knob_size = self.h - 8
        knob_x = (self.w - knob_size - 4) if self.val else 4
        painter.setBrush(QtGui.QBrush(QtGui.QColor("white")))
        painter.drawEllipse(QtCore.QRectF(knob_x, 4, knob_size, knob_size))

    def mousePressEvent(self, event):
        self.val = not self.val
        self.update()
        self.toggled.emit(self.obj_id, self.val)
        super().mousePressEvent(event)
