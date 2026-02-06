from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsTextItem


class HaspLabelItem(QGraphicsObject):
    clicked = QtCore.pyqtSignal(int)

    @property
    def obj_id(self) -> int:
        return self.obj_data.get("id", 0)

    @property
    def obj_x(self) -> int:
        return self.obj_data.get("x", 0)

    @property
    def obj_y(self) -> int:
        return self.obj_data.get("y", 0)

    @property
    def w(self) -> int:
        return self.obj_data.get("w", 100)

    @property
    def h(self) -> int:
        return self.obj_data.get("h", 30)

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
    def align(self) -> str:
        return self.obj_data.get("align", "left")

    @property
    def bg_color(self) -> str:
        return self.obj_data.get("bg_color", None)

    @property
    def border_width(self) -> int:
        return self.obj_data.get("border_width", 0)

    @property
    def border_color(self) -> str:
        return self.obj_data.get("border_color", "#FF0000")

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.parent_widget = parent_widget

        self.setPos(self.obj_x, self.obj_y)

        # Child item for text rendering
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def boundingRect(self) -> QtCore.QRectF:
        """Defines the hit-box and drawing area for the label."""
        return QtCore.QRectF(0, 0, self.w, self.h)

    def _setup_text(self):
        """Processes font, color, icons, and alignment."""
        raw_text = self.text
        if not raw_text:
            return

        pixel_size = self.text_font
        scaled_pixel_size = int(float(pixel_size) * 0.7)

        # Apply icon replacement logic if available on the parent widget
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_html'):
            processed_html = self.parent_widget._replace_unicode_with_html(raw_text, scaled_pixel_size)
            self.text_item.setHtml(processed_html)
        else:
            self.text_item.setPlainText(raw_text)

        # Color
        color = self.text_color
        self.text_item.setDefaultTextColor(QtGui.QColor(color))

        # Font (OpenHASP uses pixel sizes)
        font_size = int(self.text_font * 0.7)  # Adjust for scaling differences
        font = QtGui.QFont("Roboto Condensed", font_size)
        self.text_item.setFont(font)

        # Alignment logic
        self._align_text()

    def _align_text(self):
        """Positions the child text item based on the 'align' property."""
        align = self.align
        t_rect = self.text_item.boundingRect()

        # Vertical center is standard for HASP labels
        y_pos = (self.h - t_rect.height()) / 2

        if align == "center":
            x_pos = (self.w - t_rect.width()) / 2
        elif align == "right":
            x_pos = self.w - t_rect.width()
        else:  # left
            x_pos = 0

        self.text_item.setPos(x_pos, y_pos)

    def paint(self, painter, option, widget=None):
        """Draws optional backgrounds or borders for the label container."""
        if not painter:
            return

        # Check for background color (some HASP labels have them)
        bg_color = self.bg_color
        if bg_color:
            painter.setBrush(QtGui.QBrush(QtGui.QColor(bg_color)))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRect(self.boundingRect())

        # Draw border if specified
        border_width = self.border_width
        if border_width > 0:
            border_color = self.border_color
            pen = QtGui.QPen(QtGui.QColor(border_color))
            pen.setWidth(border_width)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())

    def mousePressEvent(self, event):
        """Labels can sometimes be clickable in HASP."""
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)
