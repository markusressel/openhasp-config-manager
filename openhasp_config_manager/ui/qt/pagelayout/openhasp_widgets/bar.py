from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush, QPen, QFont
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsTextItem


class HaspBarItem(QGraphicsObject):
    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.parent_widget = parent_widget
        self.obj_id = obj_data.get("id", 0)

        # Native Dimensions
        self.w = obj_data.get("w", 50)
        self.h = obj_data.get("h", 50)
        self.setPos(obj_data.get("x", 0), obj_data.get("y", 0))

        # Bar Values
        self.min_val = obj_data.get("min", 0)
        self.max_val = obj_data.get("max", 100)
        self.val = obj_data.get("val", 0)

        # Setup Text Child
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, self.w, self.h)

    def _setup_text(self):
        raw_text = self.obj_data.get("text", "")
        if not raw_text:
            return

        # Use your icon replacement logic
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_icons'):
            text = self.parent_widget._replace_unicode_with_icons(raw_text)
        else:
            text = raw_text

        self.text_item.setPlainText(text)
        self.text_item.setDefaultTextColor(QColor(self.obj_data.get("text_color", "#FFFFFF")))

        font_size = self.obj_data.get("text_font", 25)
        self.text_item.setFont(QFont("Roboto Condensed", font_size))

        # Center text within the bar
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.w - t_rect.width()) / 2,
            (self.h - t_rect.height()) / 2
        )

    def paint(self, painter, option, widget=None):
        if not painter:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 1. Draw Background (The Track)
        bg_color = self.obj_data.get("bg_color", "purple")
        # Your logic used 'radius' or 'height' for full rounding
        radius = self.obj_data.get("radius", self.h)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        # Background is usually a dimmer version or specific color
        painter.setBrush(QBrush(QColor(bg_color).lighter(50)))
        painter.drawRoundedRect(self.boundingRect(), radius, radius)

        # 2. Draw Progress (The Indicator)
        # Calculate width based on value percentage
        range_val = self.max_val - self.min_val
        if range_val > 0:
            progress_pct = (self.val - self.min_val) / range_val
            progress_pct = max(0, min(progress_pct, 1))  # Clamp 0.0 - 1.0

            indicator_w = self.w * progress_pct
            if indicator_w > 0:
                indicator_rect = QtCore.QRectF(0, 0, indicator_w, self.h)
                painter.setBrush(QBrush(QColor(bg_color)))
                painter.drawRoundedRect(indicator_rect, radius, radius)

        # 3. Draw Border if exists
        border_width = self.obj_data.get("border_width", 0)
        if border_width > 0:
            pen = QPen(QColor(self.obj_data.get("border_color", "#FFFFFF")))
            pen.setWidth(border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.boundingRect(), radius, radius)