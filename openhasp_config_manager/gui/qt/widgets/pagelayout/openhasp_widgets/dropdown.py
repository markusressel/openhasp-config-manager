from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    line_lead,
    number,
    option_lines,
    plate_font,
    round_pen,
    selected_index,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULTS = {
    **TRACK_DEFAULTS,
    "bg_color@4": INDICATOR_DEFAULTS["bg_color"],
    "bg_grad_color@4": INDICATOR_DEFAULTS["bg_grad_color"],
}
# measured on a plate: the selected entry starts this far from the top left corner (the first line of a label does) and leaves room
# for the symbol on the right, which sits this far from the right edge and follows the size of the font
_TEXT_OFFSET = 6
_SYMBOL_RESERVE = 30
_SYMBOL_MARGIN = 7
# the symbol: a chevron that is a quarter of the font wide and half of that deep, drawn with a thin line
_SYMBOL_DEPTH = 0.5
_SYMBOL_LINE_WIDTH = 1.5
# the directions of the dropdown (`direction`) as the way the symbol points: down, up, left, right
_SYMBOL_DIRECTIONS = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}


class HaspDropdownItem(EditableWidget):
    """
    A closed dropdown: the selected entry of `options` (by `val`) and an arrow. The open list is not drawn.
    See https://www.openhasp.com/0.7.0/design/objects/dropdown/
    """

    @property
    def selected_text(self) -> str:
        options = option_lines(self.obj_data.get("options"))
        index = selected_index(self.obj_data)
        return options[index] if 0 <= index < len(options) else ""

    def paint(self, painter, option, widget=None):
        # the box is a track, a disabled dropdown has the blue of the indicator
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DEFAULTS))

        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        _, _, right, _ = padding(self, Part.MAIN)
        left, top = (number(self.style(f"pad_{side}", _TEXT_OFFSET), _TEXT_OFFSET) for side in ("left", "top"))
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE))
        draw_text(
            painter,
            self.obj_rect.adjusted(left, top, -(_SYMBOL_RESERVE + right), 0),
            self.selected_text,
            color,
            font,
            "left",
            "top",
        )

        size = font.pixelSize()
        center = QtCore.QPointF(
            self.obj_w - _SYMBOL_MARGIN - size / 2 - right, top + (QtGui.QFontMetricsF(font).height() + line_lead(font)) / 2
        )
        direction = int(number(self.obj_data.get("direction"), 0))
        dx, dy = _SYMBOL_DIRECTIONS.get(direction, _SYMBOL_DIRECTIONS[0])
        tip = center + QtCore.QPointF(dx, dy) * size / 4 * _SYMBOL_DEPTH
        back = center - QtCore.QPointF(dx, dy) * size / 4 * _SYMBOL_DEPTH
        side = QtCore.QPointF(-dy, dx) * size / 4
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(round_pen(color, _SYMBOL_LINE_WIDTH))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QtGui.QPolygonF([back + side, tip, back - side]))
        painter.restore()
        super().paint(painter, option, widget)
