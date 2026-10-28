from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_TEXT,
    draw_text,
    number,
    option_lines,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULTS = {
    **TRACK_DEFAULTS,
    "bg_color@4": INDICATOR_DEFAULTS["bg_color"],
    "bg_grad_color@4": INDICATOR_DEFAULTS["bg_grad_color"],
}
_PADDING = 10
_ARROW_SIZE = 5


class HaspDropdownItem(EditableWidget):
    """
    A closed dropdown: the selected entry of `options` (by `val`) and an arrow. The open list is not drawn.
    See https://www.openhasp.com/0.7.0/design/objects/dropdown/
    """

    @property
    def selected_text(self) -> str:
        options = option_lines(self.obj_data.get("options"))
        index = int(number(self.obj_data.get("val"), 0))
        return options[index] if 0 <= index < len(options) else ""

    def paint(self, painter, option, widget=None):
        # the box is a track, a disabled dropdown has the blue of the indicator
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DEFAULTS))

        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        left, top, right, bottom = padding(self, Part.MAIN, 0)
        text_rect = self.obj_rect.adjusted(_PADDING + left, top, -(_PADDING * 3 + right), -bottom)
        draw_text(painter, text_rect, self.selected_text, color, plate_font(self.style("text_font", 25)), "left")

        # the symbol shows the direction the list opens (0 down, 1 up, 2 left, 3 right)
        center = QtCore.QPointF(self.obj_w - _PADDING * 1.5 - right, self.obj_h / 2)
        direction = int(number(self.obj_data.get("direction"), 0))
        dx, dy = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}.get(direction, (0, 1))
        tip = center + QtCore.QPointF(dx, dy) * _ARROW_SIZE * 0.6
        back = center - QtCore.QPointF(dx, dy) * _ARROW_SIZE * 0.6
        side = QtCore.QPointF(-dy, dx) * _ARROW_SIZE
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QtGui.QPen(
                color, 1.5, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap, QtCore.Qt.PenJoinStyle.RoundJoin
            )
        )
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QtGui.QPolygonF([back + side, tip, back - side]))
        painter.restore()
        super().paint(painter, option, widget)
