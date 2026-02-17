from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspSliderItem(EditableWidget):
    # Signal to notify when the value changes via mouse interaction
    valueChanged = QtCore.pyqtSignal(int, int)  # (object_id, new_value)

    @property
    def min_val(self) -> int:
        return self.obj_data.get("min", 0)

    @property
    def max_val(self) -> int:
        return self.obj_data.get("max", 100)

    @property
    def val(self) -> int:
        return self.obj_data.get("val", 0)

    @property
    def radius(self) -> int:
        return self.obj_data.get("radius", 0)

    @property
    def knob_radius(self) -> int:
        return self.obj_data.get("radius20", 10)

    @property
    def track_color(self) -> str:
        return self.obj_data.get("bg_color", "gray")

    @property
    def knob_color(self) -> str:
        return self.obj_data.get("bg_color20", "lightgray")

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

        self._val = self.val  # Internal value to track changes

        # Native OpenHASP coordinates
        self.setPos(self.obj_x, self.obj_y)

        # Interactivity
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QtCore.QRectF:
        """
        We expand the bounding rect slightly to ensure the knob doesn't
        get clipped if it is taller than the slider track.
        """
        margin = max(0.0, self.knob_radius - (self.obj_h / 2))
        return QtCore.QRectF(-margin, -margin, self.obj_w + (margin * 2), self.obj_h + (margin * 2))

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 1. Draw the Background Track
        track_rect = QtCore.QRectF(0, 0, self.obj_w, self.obj_h)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.track_color)))
        painter.drawRoundedRect(track_rect, self.radius, self.radius)

        # 2. Calculate Knob Position
        # Range check to avoid division by zero
        range_val = self.max_val - self.min_val
        if range_val <= 0:
            progress_pct = 0
        else:
            progress_pct = (self._val - self.min_val) / range_val
            progress_pct = max(0.0, min(progress_pct, 1))

        # 3. Draw the Knob (The "scaled circle")
        # Center the knob on the track based on current value
        knob_center_x = self.obj_w * progress_pct
        knob_center_y = self.obj_h / 2

        painter.setBrush(QBrush(QColor(self.knob_color)))
        painter.drawEllipse(
            QtCore.QPointF(knob_center_x, knob_center_y),
            self.knob_radius,
            self.knob_radius,
        )

        super().paint(painter, option, widget)

    # --- Interaction Logic ---

    def mousePressEvent(self, event):
        self._update_value_from_pos(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._update_value_from_pos(event.pos())
        super().mouseMoveEvent(event)

    def _update_value_from_pos(self, local_pos):
        """Calculates value based on where the mouse is on the track."""
        # Clamp mouse X between 0 and width
        rel_x = max(0, min(local_pos.x(), self.obj_w))
        pct = rel_x / self.obj_w

        new_val = int(self.min_val + (pct * (self.max_val - self.min_val)))

        if new_val != self._val:
            self._val = new_val
            self.update()  # Triggers repaint
            self.valueChanged.emit(self.obj_id, self._val)
