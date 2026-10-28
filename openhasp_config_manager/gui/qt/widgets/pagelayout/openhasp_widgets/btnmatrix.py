from PyQt6 import QtCore

from typing import Optional, Tuple

from openhasp_config_manager.gui.domain.button_matrix import matrix_rows
from openhasp_config_manager.gui.domain.interaction import is_true
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
    Touched, the button under the finger looks pressed, and on release a button of a matrix with `toggle` is checked or unchecked
    (with `one_check` the others are unchecked and `val` is its index). The plate sends no action for it.
    See https://www.openhasp.com/0.7.0/design/objects/btnmatrix/
    """

    @property
    def toggles(self) -> bool:
        return is_true(self.data.get("toggle"), False)

    @property
    def one_check(self) -> bool:
        return is_true(self.data.get("one_check"), False)

    def checked_buttons(self) -> Tuple[int, ...]:
        """:return: the buttons that are checked: what touching them changed, else the `val` of a matrix with `one_check`"""
        data = self.data
        if "_checked" in data:
            return data["_checked"]
        keys = list(self.obj_data)
        # measured: the plate takes `val` only if `one_check` was set before it (the attributes are applied in the order they are written)
        if self.one_check and "val" in keys and keys.index("one_check") < keys.index("val"):
            val = int(number(data.get("val"), -1))
            return (val,) if val >= 0 else ()
        return ()

    def button_at(self, point) -> Optional[int]:
        """:return: the index of the button at a point of the plate, None if the point is between the buttons or outside"""
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        for index, (rect, _button) in enumerate(self.button_rects()):
            if rect.contains(local):
                return index
        return None

    def on_press(self, point):
        self.set_pressed(True, part=self.button_at(point))

    def on_pressing(self, point):
        # the finger moves over the buttons: the one under it is the pressed one
        index = self.button_at(point)
        if index != self.runtime.pressed_part:
            self.runtime.pressed_part = index
            self.runtime_changed()

    def on_release(self, point, short_click: bool):
        index = self.runtime.pressed_part
        self.set_pressed(False)
        if index is None or not self.toggles:
            return
        checked = self.checked_buttons()
        if self.one_check:
            checked = (index,)
            self.runtime.set(self.key, "val", index, self.obj_data)
        else:
            checked = tuple(sorted(set(checked) ^ {index}))
        self.runtime.set(self.key, "_checked", checked, self.obj_data)
        self.runtime_changed()

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
        # measured on a plate: neither a `val` nor `enabled` changes how the buttons look, a checked button does
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE))
        checked = self.checked_buttons()
        for index, (rect, button) in enumerate(self.button_rects()):
            pressed = self.runtime.is_pressed(self.key) and self.runtime.pressed_part == index
            if index in checked:
                state = State.PRESSED_TOGGLED if pressed else State.TOGGLED
            else:
                state = State.PRESSED if pressed else State.DEFAULT
            draw_box(painter, rect, box_style(self, Part.ITEMS, COMPACT_BUTTON_DEFAULTS, state))
            color = to_color(
                button.color or resolve(self, "text_color", Part.ITEMS, COMPACT_BUTTON_DEFAULTS, state), DEFAULT_TEXT
            )
            draw_text(painter, rect, button.text, color, font, self.obj_data.get("align", "center"))
        super().paint(painter, option, widget)
