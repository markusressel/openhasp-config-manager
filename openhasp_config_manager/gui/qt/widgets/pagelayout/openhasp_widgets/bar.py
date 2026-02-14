from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush, QPen, QFont
from PyQt6.QtWidgets import QGraphicsTextItem

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspBarItem(EditableWidget):

    @property
    def obj_w(self) -> int:
        return self.obj_data.get("w", 50)

    @property
    def obj_h(self) -> int:
        return self.obj_data.get("h", 50)

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
    def text(self) -> str:
        return self.obj_data.get("text", "")

    @property
    def text_color(self) -> str:
        return self.obj_data.get("text_color", "#FFFFFF")

    @property
    def text_font(self) -> int:
        return self.obj_data.get("text_font", 25)

    @property
    def bg_color(self) -> str:
        return self.obj_data.get("bg_color", "#558B2F")

    @property
    def radius(self) -> int:
        return self.obj_data.get("radius", 6)

    @property
    def border_width(self) -> int:
        return self.obj_data.get("border_width", 0)

    @property
    def border_color(self) -> str:
        return self.obj_data.get("border_color", "#FFFFFF")

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

        # Native Dimensions
        self.setPos(self.obj_x, self.obj_y)

        # Setup Text Child
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def _setup_text(self):
        raw_text = self.text
        if not raw_text:
            return

        # Use your icon replacement logic
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_icons'):
            text = self.parent_widget._replace_unicode_with_icons(raw_text)
        else:
            text = raw_text

        self.text_item.setPlainText(text)
        self.text_item.setDefaultTextColor(QColor(self.text_color))

        font_size = self.text_font
        font_size = int(font_size * 0.7)
        self.text_item.setFont(QFont("Roboto Condensed", font_size))

        # Center text within the bar
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.obj_w - t_rect.width()) / 2,
            (self.obj_h - t_rect.height()) / 2
        )

    def paint(self, painter, option, widget=None):
        local_rect = self.obj_rect

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 1. Draw Background (The Track)
        bg_color = self.bg_color
        # Your logic used 'radius' or 'height' for full rounding
        radius = self.radius

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        # Background is usually a dimmer version or specific color
        painter.setBrush(QBrush(QColor(bg_color).lighter(50)))
        painter.drawRoundedRect(local_rect, radius, radius)

        # 2. Draw Progress (The Indicator)
        # Calculate width based on value percentage
        range_val = self.max_val - self.min_val
        if range_val > 0:
            progress_pct = (self.val - self.min_val) / range_val
            progress_pct = max(0.0, min(progress_pct, 1))  # Clamp 0.0 - 1.0

            indicator_w = self.obj_w * progress_pct
            if indicator_w > 0:
                indicator_rect = QtCore.QRectF(0, 0, indicator_w, self.obj_h)
                painter.setBrush(QBrush(QColor(bg_color)))
                painter.drawRoundedRect(indicator_rect, radius, radius)

        # 3. Draw Border if exists
        border_width = self.border_width
        if border_width > 0:
            pen = QPen(QColor(self.border_color))
            pen.setWidth(border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(local_rect, radius, radius)

        super().paint(painter, option, widget)