import dataclasses

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.problems import geometry_value
from openhasp_config_manager.gui.domain.style_parts import Part, State
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import (
    box_style,
    default_value,
    draw_box,
    padding,
    text_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    plate_font,
    round_pen,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# the space between the box and the text
_GAP = 0
_DEFAULT_TEXT = "Checkbox"
# measured on a plate: the box is this many pixels per pixel of the font and this many on top, 22 for font 12 and 46 for font 32
_BOX_PER_FONT_PIXEL = 1.2
_BOX_EXTRA = 7.6
# the check mark is a symbol of 11 x 8 pixels, whatever the size of the box: these are its points relative to the middle of the box
_MARK_POINTS = ((-4.5, 1.5), (-1.5, 4.5), (5.5, -2.5))
_MARK_LINE_WIDTH = 1.5

# the box (part 1): dark, blue while checked
BULLET_DEFAULTS = {
    **TRACK_DEFAULTS,
    "border_opa": 84,
    "bg_color@1": INDICATOR_DEFAULTS["bg_color"],
    "bg_grad_color@1": INDICATOR_DEFAULTS["bg_grad_color"],
    "border_width@1": 1,
    "border_color@1": "#645350",
    "border_opa@1": 61,
    "bg_color@5": "#83898B",
}


class HaspCheckboxItem(EditableWidget):
    """
    A box with a check mark and a text. On the plate the size follows the font and the text: `w` and `h` are ignored.
    See https://www.openhasp.com/0.7.0/design/objects/checkbox/
    """

    def own_style(self, name: str, part: Part, state: State):
        if part != Part.MAIN:
            return super().own_style(name, part, state)
        # measured on a plate: every part but the box (1) styles the background behind the box and the text
        for candidate in (Part.MAIN, Part.KNOB, Part.ITEMS_BACKGROUND, Part.ITEMS, Part.SELECTED):
            found = super().own_style(name, candidate, state)
            if found is not None:
                return found
        return None

    @property
    def checked(self) -> bool:
        return self.is_toggled

    @property
    def text(self) -> str:
        return str(self.obj_data.get("text", _DEFAULT_TEXT))

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", DEFAULT_FONT_SIZE))

    @property
    def box_size(self) -> int:
        return round(self.font.pixelSize() * _BOX_PER_FONT_PIXEL + _BOX_EXTRA)

    @property
    def obj_w(self) -> int:
        left, _, right, _ = padding(self, Part.MAIN)
        return round(left + right + self.box_size + _GAP + QtGui.QFontMetrics(self.font).horizontalAdvance(self.text))

    @property
    def obj_h(self) -> int:
        _, top, _, bottom = padding(self, Part.MAIN)
        return round(top + bottom + self.box_size)

    @property
    def _offset_y(self) -> float:
        """On the plate the checkbox is centered vertically in the `h` of the object (its size follows the font and the text)."""
        _, top, _, bottom = padding(self, Part.MAIN)
        # measured: the padding moves the background, a padding on the top up and one on the bottom down
        return (geometry_value(self.obj_data, "h") - self.obj_h) / 2 + bottom - top

    @property
    def obj_rect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, self._offset_y, self.obj_w, self.obj_h)

    def paint(self, painter, option, widget=None):
        # the main part: the background behind the box and the text, there is none by default
        draw_box(painter, self.obj_rect, box_style(self))

        left, top, _, _ = padding(self, Part.MAIN)
        top += self._offset_y
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
            painter.setPen(round_pen(QtGui.QColor(DEFAULT_TEXT), _MARK_LINE_WIDTH))
            painter.drawPolyline(QtGui.QPolygonF([box.center() + QtCore.QPointF(x, y) for x, y in _MARK_POINTS]))
            painter.restore()

        text_rect = QtCore.QRectF(left + self.box_size + _GAP, top, self.obj_w - left - self.box_size - _GAP, self.box_size)
        draw_text(painter, text_rect, self.text, text_color(self), self.font, "left")
        super().paint(painter, option, widget)
