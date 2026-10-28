from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part

from openhasp_config_manager.gui.domain.button_matrix import matrix_rows
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import BUTTON_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_TEXT,
    draw_text,
    line_lead,
    plate_font,
    to_color,
    wrap_lines,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: the buttons are this high and this far from the edge of the box and from each other
_PADDING = 12
_BUTTON_HEIGHT = 50
_TOP = 6
_GAP = 6
_DEFAULT_SCREEN = (480, 320)
# a track with a white glow around it
_DEFAULTS = {**TRACK_DEFAULTS, "shadow_width": 30, "shadow_color": "#FFFFFF", "shadow_opa": 90}
_BUTTON_DEFAULTS = {**BUTTON_DEFAULTS, "radius": 4}


class HaspMessageBoxItem(EditableWidget):
    """
    A pop-up with a `text` and a button for every entry of `options` (`["OK"]` by default). On the plate it is always in the middle of
    the screen (`x` and `y` are ignored) and goes away when a button is pressed; the preview shows it like any other object.
    See https://www.openhasp.com/0.7.0/design/objects/msgbox/
    """

    def _screen_size(self):
        scene = self.parent_widget.scene() if self.parent_widget is not None and hasattr(self.parent_widget, "scene") else None
        rect = scene.sceneRect() if scene is not None else None
        return (rect.width(), rect.height()) if rect is not None and not rect.isEmpty() else _DEFAULT_SCREEN

    def text_lines(self):
        """:return: the lines of the text, wrapped at the width of the box"""
        return wrap_lines(self.font, str(self.obj_data.get("text", "")), self.obj_w - 2 * _PADDING)

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", 24))

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

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DEFAULTS))

        font = self.font
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        for index, line in enumerate(self.text_lines()):
            line_rect = QtCore.QRectF(_PADDING, _TOP + index * self.line_height, self.obj_w - 2 * _PADDING, self.line_height)
            draw_text(painter, line_rect, line, color, font, "center", "top")

        buttons = self.buttons()
        if buttons:
            width = (self.obj_w - 2 * _PADDING - _GAP * (len(buttons) - 1)) / len(buttons)
            for index, text in enumerate(buttons):
                rect = QtCore.QRectF(
                    _PADDING + index * (width + _GAP), self.obj_h - _PADDING - _BUTTON_HEIGHT, width, _BUTTON_HEIGHT
                )
                draw_box(painter, rect, box_style(self, Part.ITEMS, _BUTTON_DEFAULTS))
                draw_text(painter, rect, text, to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT), font)
        super().paint(painter, option, widget)
