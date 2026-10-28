import dataclasses

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.fonts import font_size
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, default_value, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import draw_text, number, plate_font, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# the space between the box and the text
_GAP = 12
_DEFAULT_TEXT = "Checkbox"
_DEFAULT_FONT = 25

# the box (part 1): dark, blue while checked
BULLET_DEFAULTS = {
    **TRACK_DEFAULTS,
    "bg_color@1": INDICATOR_DEFAULTS["bg_color"],
    "bg_grad_color@1": INDICATOR_DEFAULTS["bg_grad_color"],
}


class HaspCheckboxItem(EditableWidget):
    """
    A box with a check mark and a text. On the plate the size follows the font and the text: `w` and `h` are ignored.
    See https://www.openhasp.com/0.7.0/design/objects/checkbox/
    """

    @property
    def checked(self) -> bool:
        return self.is_toggled

    @property
    def text(self) -> str:
        return str(self.obj_data.get("text", _DEFAULT_TEXT))

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", _DEFAULT_FONT))

    @property
    def box_size(self) -> int:
        """Measured on a plate: the box is a third bigger than the font, plus 4 pixels."""
        return round(font_size(self.style("text_font", _DEFAULT_FONT), _DEFAULT_FONT) * 4 / 3 + 3)

    @property
    def obj_w(self) -> int:
        left, _, right, _ = padding(self, Part.MAIN)
        return round(left + right + self.box_size + _GAP + QtGui.QFontMetrics(self.font).horizontalAdvance(self.text))

    @property
    def obj_h(self) -> int:
        _, top, _, bottom = padding(self, Part.MAIN)
        return round(top + bottom + self.box_size)

    def paint(self, painter, option, widget=None):
        # the main part: the background behind the box and the text, there is none by default
        draw_box(painter, self.obj_rect, box_style(self))

        left, top, _, _ = padding(self, Part.MAIN)
        box = QtCore.QRectF(left, top, self.box_size, self.box_size)
        style = box_style(self, Part.INDICATOR, BULLET_DEFAULTS)
        # measured on a plate: the colors of the box can't be changed with `bg_color1x`, only the rest of its style
        style = dataclasses.replace(
            style,
            bg_color=to_color(default_value(BULLET_DEFAULTS, "bg_color", self.state), "#FFFFFF"),
            bg_grad_color=to_color(default_value(BULLET_DEFAULTS, "bg_grad_color", self.state), "#FFFFFF"),
        )
        draw_box(painter, box, style)

        if self.checked:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            pen = QtGui.QPen(QtGui.QColor("#FFFFFF"), 1.5)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                QtGui.QPolygonF(
                    [
                        box.topLeft() + QtCore.QPointF(box.width() * 0.3, box.height() * 0.52),
                        box.topLeft() + QtCore.QPointF(box.width() * 0.44, box.height() * 0.66),
                        box.topLeft() + QtCore.QPointF(box.width() * 0.72, box.height() * 0.36),
                    ]
                )
            )
            painter.restore()

        color = to_color(self.style("text_color", None), "#FFFFFF")
        color.setAlphaF(max(0.0, min(number(self.style("text_opa", 255), 255) / 255, 1.0)))
        text_rect = QtCore.QRectF(left + self.box_size + _GAP, top, self.obj_w - left - self.box_size - _GAP, self.box_size)
        draw_text(painter, text_rect, self.text, color, self.font, "left")
        super().paint(painter, option, widget)
