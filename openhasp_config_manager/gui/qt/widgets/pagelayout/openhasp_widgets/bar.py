from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush, QPen, QFont
from PyQt6.QtWidgets import QGraphicsTextItem

from openhasp_config_manager.gui.domain.fonts import font_size
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TRACK,
    number,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


# measured on a plate: the indicator of a bar is this far from the edges of its track (the real default is in the theme of openHASP)
_DEFAULT_PADDING = 6
_DEFAULT_RADIUS = 6


def _draw_rounded(painter, rect: QtCore.QRectF, radius: float):
    """Like LVGL, a radius is never more than half of the shorter side (Qt would stretch the corners to ellipses)."""
    radius = min(radius, rect.width() / 2, rect.height() / 2)
    painter.drawRoundedRect(rect, radius, radius)


class HaspBarItem(EditableWidget):
    @property
    def min_val(self) -> int:
        return self.obj_data.get("min", 0)

    @property
    def max_val(self) -> int:
        return self.obj_data.get("max", 100)

    @property
    def val(self) -> int:
        return self.obj_data.get("val", 20)

    @property
    def text(self) -> str:
        return self.obj_data.get("text", "")

    @property
    def text_color(self) -> str:
        return self.obj_data.get("text_color", "#FFFFFF")

    @property
    def text_font(self) -> float:
        return font_size(self.obj_data.get("text_font"))

    @property
    def bg_color(self) -> QColor:
        """The color of the track (the main part)."""
        return to_color(self.style("bg_color"), DEFAULT_TRACK)

    @property
    def indicator_color(self) -> QColor:
        return to_color(self.style("bg_color", None, Part.INDICATOR), DEFAULT_ACCENT)

    @property
    def radius(self) -> float:
        return max(number(self.style("radius", _DEFAULT_RADIUS), _DEFAULT_RADIUS), 0)

    @property
    def indicator_radius(self) -> float:
        return max(number(self.style("radius", self.radius, Part.INDICATOR), self.radius), 0)

    @property
    def border_width(self) -> int:
        return self.obj_data.get("border_width", 0)

    @property
    def border_color(self) -> str:
        return self.obj_data.get("border_color", "#FFFFFF")

    def _indicator_rect(self) -> QtCore.QRectF:
        """The place of the indicator at 100%: the object without the padding of the main part, like LVGL."""
        padding = [number(self.style(f"pad_{side}"), _DEFAULT_PADDING) for side in ("left", "top", "right", "bottom")]
        return self.obj_rect.adjusted(padding[0], padding[1], -padding[2], -padding[3])

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data, parent_widget)

        # Native Dimensions
        self.setPos(self.obj_x, self.obj_y)

        # Setup Text Child
        self.text_item = QGraphicsTextItem(parent=self)
        self._setup_text()

    def _setup_text(self):
        raw_text = self.text
        if not raw_text:
            self.text_item.setPlainText("")
            return

        # Use your icon replacement logic
        if self.parent_widget and hasattr(self.parent_widget, "_replace_unicode_with_icons"):
            text = self.parent_widget._replace_unicode_with_icons(raw_text)
        else:
            text = raw_text

        self.text_item.setPlainText(text)
        self.text_item.setDefaultTextColor(QColor(self.text_color))

        pixel_size = int(self.text_font * 0.7)
        self.text_item.setFont(QFont("Roboto Condensed", pixel_size))

        # Center text within the bar
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.obj_w - t_rect.width()) / 2,
            (self.obj_h - t_rect.height()) / 2,
        )

    def _on_data_changed(self):
        self._setup_text()

    def paint(self, painter, option, widget=None):
        local_rect = self.obj_rect

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 1. Draw Background (The Track)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.bg_color))
        _draw_rounded(painter, local_rect, self.radius)

        # 2. Draw Progress (The Indicator), inside of the track
        range_val = self.max_val - self.min_val
        if range_val > 0:
            progress_pct = (self.val - self.min_val) / range_val
            progress_pct = max(0.0, min(progress_pct, 1))  # Clamp 0.0 - 1.0

            full = self._indicator_rect()
            indicator_rect = QtCore.QRectF(full.x(), full.y(), full.width() * progress_pct, full.height())
            if indicator_rect.width() > 0:
                painter.setBrush(QBrush(self.indicator_color))
                _draw_rounded(painter, indicator_rect, self.indicator_radius)

        # 3. Draw Border if exists
        border_width = self.border_width
        if border_width > 0:
            pen = QPen(QColor(self.border_color))
            pen.setWidth(border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            _draw_rounded(painter, local_rect, self.radius)

        super().paint(painter, option, widget)
