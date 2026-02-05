from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import QGraphicsObject


class HaspSliderItem(QGraphicsObject):
    # Signal to notify when the value changes via mouse interaction
    valueChanged = QtCore.pyqtSignal(int, int)  # (object_id, new_value)

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.parent_widget = parent_widget
        self.obj_id = obj_data.get("id", 0)

        # Native OpenHASP coordinates
        self.w = obj_data.get("w", 160)
        self.h = obj_data.get("h", 20)
        self.setPos(obj_data.get("x", 0), obj_data.get("y", 0))

        # Slider Range & Value
        self.min_val = obj_data.get("min", 0)
        self.max_val = obj_data.get("max", 100)
        self.val = obj_data.get("val", 0)

        # Visual Properties from your original logic
        self.radius = obj_data.get("radius", 0)
        self.knob_radius = obj_data.get("radius20", 10)
        self.track_color = obj_data.get("bg_color", "gray")
        self.knob_color = obj_data.get("bg_color20", "lightgray")

        # Interactivity
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QtCore.QRectF:
        """
        We expand the bounding rect slightly to ensure the knob doesn't
        get clipped if it is taller than the slider track.
        """
        margin = max(0, self.knob_radius - (self.h / 2))
        return QtCore.QRectF(-margin, -margin, self.w + (margin * 2), self.h + (margin * 2))

    def paint(self, painter, option, widget=None):
        if not painter:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 1. Draw the Background Track
        track_rect = QtCore.QRectF(0, 0, self.w, self.h)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.track_color)))
        painter.drawRoundedRect(track_rect, self.radius, self.radius)

        # 2. Calculate Knob Position
        # Range check to avoid division by zero
        range_val = self.max_val - self.min_val
        if range_val <= 0:
            progress_pct = 0
        else:
            progress_pct = (self.val - self.min_val) / range_val
            progress_pct = max(0, min(progress_pct, 1))

        # 3. Draw the Knob (The "scaled circle")
        # Center the knob on the track based on current value
        knob_center_x = self.w * progress_pct
        knob_center_y = self.h / 2

        painter.setBrush(QBrush(QColor(self.knob_color)))
        painter.drawEllipse(
            QtCore.QPointF(knob_center_x, knob_center_y),
            self.knob_radius,
            self.knob_radius
        )

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
        rel_x = max(0, min(local_pos.x(), self.w))
        pct = rel_x / self.w

        new_val = int(self.min_val + (pct * (self.max_val - self.min_val)))

        if new_val != self.val:
            self.val = new_val
            self.update()  # Triggers repaint
            self.valueChanged.emit(self.obj_id, self.val)