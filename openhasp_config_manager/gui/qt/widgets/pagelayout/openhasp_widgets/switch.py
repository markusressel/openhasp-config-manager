from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspSwitchItem(EditableWidget):
    toggled = QtCore.pyqtSignal(int, bool)

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
        super().__init__(obj_data)

        self._val = self.val  # Store the current state for toggling

        self.setPos(self.obj_x, self.obj_y)

    def paint(self, painter, option, widget=None):
        local_rect = self.obj_rect
        
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Track color based on state
        color = self.bg_color if self._val else "#313131"
        painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(local_rect, self.obj_h / 2, self.obj_h / 2)

        # Knob
        knob_size = self.obj_h - 8
        knob_x = (self.obj_w - knob_size - 4) if self._val else 4
        painter.setBrush(QtGui.QBrush(QtGui.QColor(self.knob_color)))
        painter.drawEllipse(QtCore.QRectF(knob_x, 4, knob_size, knob_size))

        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        self._val = not self._val
        self.update()
        self.toggled.emit(self.obj_id, self._val)
        super().mousePressEvent(event)
