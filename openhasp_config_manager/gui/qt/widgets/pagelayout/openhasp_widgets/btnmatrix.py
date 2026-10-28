from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.button_matrix import matrix_rows
from openhasp_config_manager.gui.domain.style_parts import Part, State
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding, resolve
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import COMPACT_BUTTON_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INNER_PADDING,
    TRACK_DEFAULTS,
    TRACK_PADDING,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    number,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspButtonMatrixItem(EditableWidget):
    """
    Rows of buttons from `options` (`"\\n"` starts a new row, `#RRGGBB text#` colors a label). Every row has the same height and
    the buttons of a row share its width. The matrix itself (the main
    part) is a track, the buttons are the items (part 4) and `pad_inner` is the space between them.
    See https://www.openhasp.com/0.7.0/design/objects/btnmatrix/
    """

    def button_rects(self):
        """:return: the rect of every button with its MatrixButton, in the order of `options`"""
        rows = matrix_rows(self.obj_data.get("options", "Text"))
        left, top, right, bottom = padding(self, Part.MAIN, TRACK_PADDING)
        gap = number(self.style("pad_inner"), INNER_PADDING)
        inner = self.obj_rect.adjusted(left, top, -right, -bottom)
        result = []
        for row_index, row in enumerate(rows):
            height = (inner.height() - gap * (len(rows) - 1)) / len(rows)
            width = (inner.width() - gap * (len(row) - 1)) / len(row)
            for column, button in enumerate(row):
                rect = QtCore.QRectF(
                    inner.left() + column * (width + gap), inner.top() + row_index * (height + gap), width, height
                )
                result.append((rect, button))
        return result

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))
        # measured on a plate: neither a `val` nor `enabled` changes how the buttons look
        state = State.DEFAULT
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE))
        for rect, button in self.button_rects():
            draw_box(painter, rect, box_style(self, Part.ITEMS, COMPACT_BUTTON_DEFAULTS, state))
            color = to_color(
                button.color or resolve(self, "text_color", Part.ITEMS, COMPACT_BUTTON_DEFAULTS, state), DEFAULT_TEXT
            )
            draw_text(painter, rect, button.text, color, font, self.obj_data.get("align", "center"))
        super().paint(painter, option, widget)
