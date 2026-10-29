from PyQt6 import QtCore, QtGui

from typing import Optional

from openhasp_config_manager.gui.domain.button_matrix import matrix_rows
from openhasp_config_manager.gui.domain.source.placeholders import shown_text
from openhasp_config_manager.gui.domain.style_parts import Part, State
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import COMPACT_BUTTON_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INNER_PADDING, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    line_lead,
    plate_font,
    to_color,
    wrap_lines,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: the buttons are this high and this far from the edge of the box, the text this far from the top
_PADDING = 12
_BUTTON_HEIGHT = 50
_TOP = 6
_DEFAULT_SCREEN = (480, 320)
# a track with a white glow around it
_DEFAULTS = {**TRACK_DEFAULTS, "shadow_width": 30, "shadow_color": "#FFFFFF", "shadow_opa": 90}


class HaspMessageBoxItem(EditableWidget):
    """
    A pop-up with a `text` and a button for every entry of `options` (`["OK"]` by default). On the plate it is always in the middle of
    the screen (`x` and `y` are ignored) and goes away when a button is released; the preview shows it like any other object, and
    hides it when a button was touched (until the interactions are reset).
    See https://www.openhasp.com/0.7.0/design/objects/msgbox/
    """

    def _screen_size(self):
        scene = self.parent_widget.scene() if self.parent_widget is not None and hasattr(self.parent_widget, "scene") else None
        rect = scene.sceneRect() if scene is not None else None
        return (rect.width(), rect.height()) if rect is not None and not rect.isEmpty() else _DEFAULT_SCREEN

    def text_lines(self):
        """:return: the lines of the text, wrapped at the width of the box"""
        return wrap_lines(self.font, str(shown_text(self.obj_data.get("text", ""))), self.obj_w - 2 * _PADDING)

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", DEFAULT_FONT_SIZE))

    @property
    def line_height(self) -> float:
        return QtGui.QFontMetricsF(self.font).lineSpacing() + line_lead(self.font)

    @property
    def obj_h(self) -> int:
        """Measured on a plate: the height follows the text and the buttons (`h` is ignored)."""
        return round(_TOP + len(self.text_lines()) * self.line_height + _PADDING + _BUTTON_HEIGHT + _PADDING)

    @property
    def obj_x(self) -> int:
        return round((self._screen_size()[0] - self.obj_w) / 2)

    @property
    def obj_y(self) -> int:
        return round((self._screen_size()[1] - self.obj_h) / 2)

    def buttons(self):
        options = self.obj_data.get("options", ["OK"])
        return [button.text for row in matrix_rows(options) for button in row]

    def button_rects(self):
        """:return: the rect of every button, in the order of `options`"""
        buttons = self.buttons()
        if not buttons:
            return []
        width = (self.obj_w - 2 * _PADDING - INNER_PADDING * (len(buttons) - 1)) / len(buttons)
        return [
            QtCore.QRectF(
                _PADDING + index * (width + INNER_PADDING), self.obj_h - _PADDING - _BUTTON_HEIGHT, width, _BUTTON_HEIGHT
            )
            for index in range(len(buttons))
        ]

    def button_at(self, point) -> Optional[int]:
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        return next((index for index, rect in enumerate(self.button_rects()) if rect.contains(local)), None)

    def on_press(self, point):
        index = self.button_at(point)
        # only a button looks pressed, never the box
        self.set_pressed(True, part=-1 if index is None else index)

    def on_pressing(self, point):
        index = self.button_at(point)
        part = -1 if index is None else index
        if self.runtime.is_pressed(self.key) and part != self.runtime.pressed_part:
            self.runtime.pressed_part = part
            self.runtime_changed()

    def on_release(self, point, short_click: bool):
        index = self.runtime.pressed_part
        self.set_pressed(False)
        if index is not None and index >= 0 and self.button_at(point) == index:
            # `lv_msgbox_start_auto_close(obj, 0)`: it goes away at once
            self.runtime.closed.add(self.key)
            self.runtime_changed()

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DEFAULTS))

        font = self.font
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        for index, line in enumerate(self.text_lines()):
            line_rect = QtCore.QRectF(_PADDING, _TOP + index * self.line_height, self.obj_w - 2 * _PADDING, self.line_height)
            draw_text(painter, line_rect, line, color, font, "center", "top")

        for index, (rect, text) in enumerate(zip(self.button_rects(), self.buttons())):
            pressed = self.runtime.is_pressed(self.key) and self.runtime.pressed_part == index
            draw_box(
                painter,
                rect,
                box_style(self, Part.ITEMS, COMPACT_BUTTON_DEFAULTS, State.PRESSED if pressed else State.DEFAULT),
            )
            draw_text(painter, rect, text, to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT), font)
        super().paint(painter, option, widget)
