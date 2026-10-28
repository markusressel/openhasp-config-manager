import dataclasses

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.fonts import font_size
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import (
    GRADIENT_VERTICAL,
    box_style,
    capped_radius,
    draw_box,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    DEFAULT_RADIUS,
    INDICATOR_DEFAULTS,
    TRACK_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    number,
    option_lines,
    plate_font,
    selected_index,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: the height of a row is this many pixels per pixel of the font and this many on top (45 for font 24, 31 for 12)
_ROW_PER_FONT_PIXEL = 1.167
_ROW_EXTRA = 17
# the space between the text and the left and right edge of the roller
_TEXT_PADDING = 8
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
        return plate_font(self.style("text_font", DEFAULT_FONT_SIZE))

    @property
    def row_height(self) -> float:
        return font_size(self.style("text_font", DEFAULT_FONT_SIZE), DEFAULT_FONT_SIZE) * _ROW_PER_FONT_PIXEL + _ROW_EXTRA

    @property
    def obj_h(self) -> int:
        rows = self.rows
        return round(rows * self.row_height) if rows else super().obj_h

    def entry_rows(self):
        """:return: (top of the row, entry or None, whether it is the selected one) for every row that is at least partly visible"""
        options = option_lines(self.obj_data.get("options"))
        selected = selected_index(self.obj_data)
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

    def _draw_mirrored_gradient(self, painter, style):
        """Measured on a plate: the background goes from `bg_color` at the top and at the bottom to `bg_grad_color` in the middle."""
        rect = self.obj_rect
        radius = capped_radius(rect, style.radius)
        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.setClipPath(clip)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        edge, middle = QtGui.QColor(style.bg_color), QtGui.QColor(style.bg_grad_color)
        edge.setAlphaF(style.bg_opa)
        middle.setAlphaF(style.bg_opa)
        for top, bottom, from_top in ((rect.top(), rect.center().y(), True), (rect.center().y(), rect.bottom(), False)):
            gradient = QtGui.QLinearGradient(0, top if from_top else bottom, 0, bottom if from_top else top)
            gradient.setColorAt(0, edge)
            gradient.setColorAt(1, middle)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.drawRect(QtCore.QRectF(rect.left(), top, rect.width(), bottom - top))
        painter.restore()

    def paint(self, painter, option, widget=None):
        main = box_style(self, Part.MAIN, TRACK_DEFAULTS)
        # the background and shadow are below the rows, the border and outline above them
        background = dataclasses.replace(main, border_width=0, outline_width=0)
        frame = dataclasses.replace(main, bg_opa=0, shadow_width=0)
        if main.bg_grad_dir == GRADIENT_VERTICAL and main.bg_opa > 0:
            self._draw_mirrored_gradient(painter, main)
            background = dataclasses.replace(background, bg_opa=0)
        draw_box(painter, self.obj_rect, background)

        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(self.obj_rect, DEFAULT_RADIUS, DEFAULT_RADIUS)
        painter.setClipPath(clip)
        align = self.obj_data.get("align", "center")
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        for top, entry, is_selected in self.entry_rows():
            row = QtCore.QRectF(0, top, self.obj_w, self.row_height)
            if is_selected:
                draw_box(
                    painter,
                    row.adjusted(main.border_width, 0, -main.border_width, 0),
                    box_style(self, Part.SELECTED, _SELECTED_DEFAULTS),
                )
            if entry is None:
                continue
            row_color = to_color(self.style("text_color", None, Part.SELECTED), color.name()) if is_selected else color
            draw_text(painter, row.adjusted(_TEXT_PADDING, 0, -_TEXT_PADDING, 0), entry, row_color, self.font, align)
        painter.restore()
        draw_box(painter, self.obj_rect, frame)
        super().paint(painter, option, widget)
