from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QGraphicsObject


class HaspSwitchItem(QGraphicsObject):
    toggled = QtCore.pyqtSignal(int, bool)

    @property
    def obj_id(self):
        return self.obj_data.get("id", 0)

    @property
    def obj_x(self) -> int:
        return self.obj_data.get("x", 0)

    @property
    def obj_y(self) -> int:
        return self.obj_data.get("y", 0)

    @property
    def w(self) -> int:
        return self.obj_data.get("w", 80)

    @property
    def h(self) -> int:
        return self.obj_data.get("h", 40)

    @property
    def val(self) -> bool:
        return bool(self.obj_data.get("val", 0))

    @property
    def bg_color(self) -> str:
        return self.obj_data.get("bg_color", "#558B2F")

    @property
    def corner_radius(self):
        return self.obj_data.get("radius00", 0)

    @property
    def knob_radius(self) -> int:
        return self.obj_data.get("radius20", 0)

    @property
    def text_font(self) -> str:
        return self.obj_data.get("text_font", 25)

    @property
    def text_color(self) -> str:
        return self.obj_data.get("text_color", None)

    @property
    def knob_color(self) -> str:
        return self.obj_data.get("bg_color20", "lightgray")

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data

        self._val = self.val  # Store the current state for toggling

        self.setPos(obj_data.get("x", 0), obj_data.get("y", 0))

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Track color based on state
        color = self.bg_color if self._val else "#313131"
        painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.boundingRect(), self.h / 2, self.h / 2)

        # Knob
        knob_size = self.h - 8
        knob_x = (self.w - knob_size - 4) if self._val else 4
        painter.setBrush(QtGui.QBrush(QtGui.QColor(self.knob_color)))
        painter.drawEllipse(QtCore.QRectF(knob_x, 4, knob_size, knob_size))

    def mousePressEvent(self, event):
        self._val = not self._val
        self.update()
        self.toggled.emit(self.obj_id, self._val)
        super().mousePressEvent(event)
