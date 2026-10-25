from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TEXT,
    DEFAULT_TRACK,
    draw_text,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# the space between the box and the text
_GAP = 8
_DEFAULT_TEXT = "Checkbox"


class HaspCheckboxItem(EditableWidget):
    """
    A box with a check mark and a text. On the plate the size follows the font and the text: `w` and `h` are ignored.
    See https://www.openhasp.com/0.7.0/design/objects/checkbox/
    """

    @property
    def checked(self) -> bool:
        return bool(self.obj_data.get("val", 0))

    @property
    def text(self) -> str:
        return str(self.obj_data.get("text", _DEFAULT_TEXT))

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", 25))

    @property
    def box_size(self) -> int:
        return QtGui.QFontMetrics(self.font).height()

    @property
    def obj_w(self) -> int:
        return self.box_size + _GAP + QtGui.QFontMetrics(self.font).horizontalAdvance(self.text)

    @property
    def obj_h(self) -> int:
        return self.box_size

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        box = QtCore.QRectF(0, 0, self.box_size, self.box_size)
        # the box is filled with the indicator color while it is checked
        fill = to_color(self.style("bg_color", DEFAULT_ACCENT, Part.INDICATOR), DEFAULT_ACCENT) if self.checked else None
        painter.setBrush(QtGui.QBrush(fill if fill else QtGui.QColor(DEFAULT_TRACK)))
        painter.setPen(QtGui.QPen(to_color(self.style("border_color", "#808080"), "#808080"), 2))
        painter.drawRoundedRect(box, 3, 3)
        if self.checked:
            pen = QtGui.QPen(QtGui.QColor(DEFAULT_TEXT), 2)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            size = self.box_size
            painter.drawPolyline(
                QtGui.QPolygonF(
                    [
                        QtCore.QPointF(size * 0.22, size * 0.52),
                        QtCore.QPointF(size * 0.42, size * 0.72),
                        QtCore.QPointF(size * 0.78, size * 0.3),
                    ]
                )
            )
        text_rect = QtCore.QRectF(self.box_size + _GAP, 0, self.obj_w - self.box_size - _GAP, self.box_size)
        draw_text(painter, text_rect, self.text, to_color(self.style("text_color"), DEFAULT_TEXT), self.font, "left")
        super().paint(painter, option, widget)
