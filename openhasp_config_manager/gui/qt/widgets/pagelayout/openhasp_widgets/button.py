from collections.abc import Callable
from typing import Dict

from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QGraphicsTextItem

from openhasp_config_manager.gui.qt.util import qBridge
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspButtonItem(EditableWidget):
    clicked = QtCore.pyqtSignal(int)

    @property
    def obj_w(self) -> int:
        return self.obj_data.get("w", 50)

    @property
    def obj_h(self) -> int:
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

    def __init__(
        self,
        obj_data: Dict,
        on_click: Callable[[Dict], None] = None,
        parent_widget=None,
    ):
        super().__init__(obj_data)
        self.parent_widget = parent_widget
        self._on_click = on_click

        # Set position in the native scene coordinate system
        self.setPos(self.obj_x, self.obj_y)

        # Setup Text Item
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

        self.clicked.connect(self._on_button_clicked)

    @qBridge()
    def _on_button_clicked(self):
        self._on_click(self.obj_data)

    def _setup_text(self):
        """Applies Rich Text (HTML) to support both regular fonts and icons."""
        raw_text = str(self.text)
        if not raw_text:
            return

        pixel_size = self.text_font
        scaled_pixel_size = int(float(pixel_size) * 0.7)

        # 1. Determine the content and font requirements
        # We use HTML to allow per-character font switching
        if self.parent_widget and hasattr(self.parent_widget, '_replace_unicode_with_html'):
            processed_html = self.parent_widget._replace_unicode_with_html(raw_text, scaled_pixel_size)
            self.text_item.setHtml(processed_html)
        else:
            self.text_item.setPlainText(raw_text)

        # 2. Set the base font for the non-icon text
        base_font = QFont("Roboto Condensed", scaled_pixel_size)
        self.text_item.setFont(base_font)

        # 3. Apply Styling
        self.text_item.setDefaultTextColor(QColor(self.text_color))

        # 4. Centering Logic
        # Note: HTML text often has a small default margin
        self.text_item.document().setDocumentMargin(0)
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.obj_w - t_rect.width()) / 2,
            (self.obj_h - t_rect.height()) / 2
        )

    def paint(self, painter, option, widget=None):
        """Draws the button shape in native coordinates."""
        local_rect = self.obj_rect

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

        rect = local_rect

        # openHASP radius can be a pixel value or very large for pill-shape
        # We ensure it doesn't exceed half the height/width
        effective_radius = min(float(self.radius), self.obj_h / 2, self.obj_w / 2)

        painter.drawRoundedRect(rect, effective_radius, effective_radius)

        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(self.obj_id)
