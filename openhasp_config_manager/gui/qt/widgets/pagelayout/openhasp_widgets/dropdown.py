from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_TEXT,
    draw_text,
    line_lead,
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
        # measured on a plate: the selected entry starts 6 pixels from the top left corner (the first line of a label does), the symbol
        # follows the size of the font
        _, _, right, _ = padding(self, Part.MAIN, 0)
        left, top = number(self.style("pad_left", 6, Part.MAIN), 6), number(self.style("pad_top", 6, Part.MAIN), 6)
        font = plate_font(self.style("text_font", 24))
        draw_text(
            painter,
            self.obj_rect.adjusted(left, top, -(_PADDING * 3 + right), 0),
            self.selected_text,
            color,
            font,
            "left",
            "top",
        )

        size = font.pixelSize()
        center = QtCore.QPointF(
            self.obj_w - 7 - size / 2 - right, top + (QtGui.QFontMetricsF(font).height() + line_lead(font)) / 2
        )
        direction = int(number(self.obj_data.get("direction"), 0))
        dx, dy = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}.get(direction, (0, 1))
        tip = center + QtCore.QPointF(dx, dy) * size / 4 * 0.5
        back = center - QtCore.QPointF(dx, dy) * size / 4 * 0.5
        side = QtCore.QPointF(-dy, dx) * size / 4
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
