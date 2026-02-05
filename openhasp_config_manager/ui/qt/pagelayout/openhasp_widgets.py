from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsTextItem


class HaspButtonItem(QGraphicsObject):
    clicked = QtCore.pyqtSignal(int)

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.obj_id = obj_data.get("id", 0)
        self.parent_widget = parent_widget  # Useful for helper methods

        # Native Dimensions
        self.x = obj_data.get("x", 0)
        self.y = obj_data.get("y", 0)
        self.w = obj_data.get("w", 50)
        self.h = obj_data.get("h", 50)
        self.radius = obj_data.get("radius", 0)

        # Set position in scene
        self.setPos(self.x, self.y)

        # Setup Text Item
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def boundingRect(self) -> QtCore.QRectF:
        """Defines the clickable area and drawing boundary."""
        return QtCore.QRectF(0, 0, self.w, self.h)

    def _setup_text(self):
        """Applies font, color, and centering for the button label."""
        raw_text = self.obj_data.get("text", "")

        # Use your existing icon replacement logic if available
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_icons'):
            processed_text = self.parent_widget._replace_unicode_with_icons(raw_text)
        else:
            processed_text = raw_text

        self.text_item.setPlainText(processed_text)

        # Font settings
        pixel_size = self.obj_data.get("text_font", 25)
        font = QFont("Roboto Condensed", pixel_size)
        self.text_item.setFont(font)

        # Color
        color = self.obj_data.get("text_color", "#FFFFFF")
        self.text_item.setDefaultTextColor(QColor(color))

        # Centering Logic
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.w - t_rect.width()) / 2,
            (self.h - t_rect.height()) / 2
        )

    def paint(self, painter, option, widget=None):
        """Draws the actual button shape."""
        if not painter:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Background
        bg_color = self.obj_data.get("bg_color", "#558B2F")
        painter.setBrush(QtGui.QBrush(QtGui.QColor(bg_color)))

        # Border
        border_width = self.obj_data.get("border_width", 0)
        if border_width > 0:
            border_color = self.obj_data.get("border_color", "#FF0000")
            pen = QtGui.QPen(QtGui.QColor(border_color))
            pen.setWidth(border_width)
            painter.setPen(pen)
        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)

        # Draw Rounded Rect
        rect = self.boundingRect()
        painter.drawRoundedRect(rect, self.radius, self.radius)

    def mousePressEvent(self, event):
        """Handle the click event."""
        # Visual feedback (optional): you could change brush color here
        # and call self.update() to simulate a 'pressed' state
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)
