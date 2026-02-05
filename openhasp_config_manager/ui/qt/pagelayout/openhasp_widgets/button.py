from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsTextItem


class HaspButtonItem(QGraphicsObject):
    clicked = QtCore.pyqtSignal(int)

    @property
    def obj_id(self) -> int:
        return self.obj_data.get("id", 0)

    @property
    def x(self) -> int:
        return self.obj_data.get("x", 0)

    @property
    def y(self) -> int:
        return self.obj_data.get("y", 0)

    @property
    def w(self) -> int:
        return self.obj_data.get("w", 50)

    @property
    def h(self) -> int:
        return self.obj_data.get("h", 50)

    @property
    def radius(self) -> int:
        return self.obj_data.get("radius", 0)

    @property
    def text(self) -> str:
        return self.obj_data.get("text", "")

    @property
    def text_font(self) -> int:
        return self.obj_data.get("text_font", 25)

    @property
    def text_color(self) -> str:
        return self.obj_data.get("text_color", "#FFFFFF")

    @property
    def bg_color(self) -> str:
        return self.obj_data.get("bg_color", "#558B2F")

    @property
    def border_width(self) -> int:
        return self.obj_data.get("border_width", 0)

    @property
    def border_color(self) -> str:
        return self.obj_data.get("border_color", "#000000")

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.parent_widget = parent_widget

        # Set position in the native scene coordinate system
        self.setPos(self.x, self.y)

        # Setup Text Item
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def boundingRect(self) -> QtCore.QRectF:
        """Defines the clickable area in native pixels."""
        return QtCore.QRectF(0, 0, self.w, self.h)

    def _setup_text(self):
        """Applies font and centering using the native pixel size with scaling correction."""
        raw_text = str(self.text)

        # Replace icons using your IntegratedIcon logic
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_icons'):
            processed_text = self.parent_widget._replace_unicode_with_icons(raw_text)
        else:
            processed_text = raw_text

        self.text_item.setPlainText(processed_text)

        # Apply the scale_factor logic here:
        # Since we are in the native scene, we don't need d_height/page_height.
        # We just apply the 0.7 adjustment to match openHASP's visual density.
        pixel_size = self.text_font

        # Correctly interpret pointsize vs TrueType in 0.7.0
        # If it's a small number like 12, 16, 24, 32, it's a fixed font.
        # If it's larger or custom, it's the TrueType size.
        scaled_pixel_size = int(float(pixel_size) * 0.7)

        font = QFont("Roboto Condensed", scaled_pixel_size)
        font.setWeight(QFont.Weight.Normal)
        self.text_item.setFont(font)

        # Text Color
        color = self.text_color
        self.text_item.setDefaultTextColor(QColor(color))

        # Centering Logic (within the native button rect)
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.w - t_rect.width()) / 2,
            (self.h - t_rect.height()) / 2
        )

    def paint(self, painter, option, widget=None):
        """Draws the button shape in native coordinates."""
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Background
        bg_color = self.bg_color
        painter.setBrush(QBrush(QColor(bg_color)))

        # Border logic from your scaled_text implementation
        border_width = self.border_width
        if border_width > 0:
            border_color = self.border_color
            pen = QPen(QColor(border_color))
            pen.setWidth(border_width)
            painter.setPen(pen)
        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)

        rect = self.boundingRect()

        # openHASP radius can be a pixel value or very large for pill-shape
        # We ensure it doesn't exceed half the height/width
        effective_radius = min(self.radius, self.h / 2, self.w / 2)

        painter.drawRoundedRect(rect, effective_radius, effective_radius)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(self.obj_id)
