from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.fonts import font_size
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
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

_DEFAULT_FONT = 25
# the selected row (part 5): the blue of the indicator, with square corners
_SELECTED_DEFAULTS = {**INDICATOR_DEFAULTS, "radius": 0}


class HaspRollerItem(EditableWidget):
    """
    A list of `options` with the selected one (`val`) in the middle, highlighted. With `rows` the height follows the rows and the
    font (`h` is ignored), without it `h` is the height and the list is cut off at the edges. In mode 1 (infinite) the list wraps around.
    See https://www.openhasp.com/0.7.0/design/objects/roller/
    """

    @property
    def rows(self):
        """:return: the number of visible rows if the object says so, else None"""
        return max(int(number(self.obj_data["rows"], 3)), 1) if "rows" in self.obj_data else None

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", _DEFAULT_FONT))

    @property
    def row_height(self) -> float:
        """Measured on a plate: 45 pixels with the default font, 31 with the font 12."""
        return font_size(self.style("text_font", _DEFAULT_FONT), _DEFAULT_FONT) * 1.077 + 18

    @property
    def obj_h(self) -> int:
        rows = self.rows
        return round(rows * self.row_height) if rows else super().obj_h

    def entry_rows(self):
        """:return: (top of the row, entry or None, whether it is the selected one) for every row that is at least partly visible"""
        options = option_lines(self.obj_data.get("options"))
        selected = int(number(self.obj_data.get("val"), 0))
        infinite = int(number(self.obj_data.get("mode"), 0)) == 1
        middle = self.obj_h / 2 - self.row_height / 2
        reach = int(self.obj_h // self.row_height) + 2
        result = []
        for offset in range(-reach, reach + 1):
            top = middle + offset * self.row_height
            if top + self.row_height <= 1 or top >= self.obj_h - 1:
                continue
            index = selected + offset
            if infinite and options:
                index %= len(options)
            result.append((top, options[index] if 0 <= index < len(options) else None, offset == 0))
        return result

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(self.obj_rect, 4, 4)
        painter.setClipPath(clip)
        align = self.obj_data.get("align", "center")
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        for top, entry, is_selected in self.entry_rows():
            row = QtCore.QRectF(0, top, self.obj_w, self.row_height)
            if is_selected:
                draw_box(painter, row, box_style(self, Part.SELECTED, _SELECTED_DEFAULTS))
            if entry is None:
                continue
            row_color = to_color(self.style("text_color", None, Part.SELECTED), color.name()) if is_selected else color
            draw_text(painter, row.adjusted(8, 0, -8, 0), entry, row_color, self.font, align)
        painter.restore()
        super().paint(painter, option, widget)
