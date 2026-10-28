from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.tabs import tab_texts
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_TEXT,
    draw_text,
    number,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_BUTTONS_TOP, _BUTTONS_BOTTOM, _BUTTONS_LEFT, _BUTTONS_RIGHT = 1, 2, 3, 4
# measured on a plate: the row of tab buttons is this high, the indicator under the active tab this thick
_BUTTON_THICKNESS = 62
_INDICATOR_THICKNESS = 5
_BAR_COLOR = "#202839"
_SIDE_BUTTON_WIDTH = 90


class HaspTabviewItem(EditableWidget):
    """
    A container with a row (or column) of tab buttons at `btn_pos`: 0 none, 1 top, 2 bottom, 3 left, 4 right. The buttons are the
    `tab` objects that have the tabview as their `parentid`; `val` is the active one. Objects on a tab are not drawn inside of it.
    The height of the button row is `pad_top40` + `pad_bottom40` on top of the default.
    See https://www.openhasp.com/0.7.0/design/objects/tabview/
    """

    def tabs(self):
        return tab_texts(getattr(self.parent_widget, "objects", []), self.obj_data)

    def button_area(self) -> QtCore.QRectF:
        """:return: where the tab buttons are, an empty rect without buttons"""
        position = int(number(self.obj_data.get("btn_pos"), _BUTTONS_TOP))
        thickness = (
            _BUTTON_THICKNESS
            + number(self.style("pad_top", 0, Part.ITEMS), 0)
            + number(self.style("pad_bottom", 0, Part.ITEMS), 0)
        )
        rect = self.obj_rect
        if position == _BUTTONS_TOP:
            return QtCore.QRectF(0, 0, rect.width(), thickness)
        if position == _BUTTONS_BOTTOM:
            return QtCore.QRectF(0, rect.height() - thickness, rect.width(), thickness)
        if position == _BUTTONS_LEFT:
            return QtCore.QRectF(0, 0, _SIDE_BUTTON_WIDTH, rect.height())
        if position == _BUTTONS_RIGHT:
            return QtCore.QRectF(rect.width() - _SIDE_BUTTON_WIDTH, 0, _SIDE_BUTTON_WIDTH, rect.height())
        return QtCore.QRectF()

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        area = self.button_area()
        tabs = self.tabs()
        if area.isEmpty() or not tabs:
            return super().paint(painter, option, widget)
        horizontal = area.width() >= area.height() and int(number(self.obj_data.get("btn_pos"), 1)) in (
            _BUTTONS_TOP,
            _BUTTONS_BOTTOM,
        )
        # the tab buttons (part 4) are one bar
        draw_box(painter, area, box_style(self, Part.ITEMS, {"bg_color": _BAR_COLOR, "bg_opa": 255, "radius": 0}))
        active = int(number(self.obj_data.get("val"), 0))
        font = plate_font(self.style("text_font", 25, Part.ITEMS))
        for index, text in enumerate(tabs):
            if horizontal:
                button = QtCore.QRectF(
                    area.left() + area.width() * index / len(tabs), area.top(), area.width() / len(tabs), area.height()
                )
            else:
                button = QtCore.QRectF(area.left(), area.top() + _BUTTON_THICKNESS * index, area.width(), _BUTTON_THICKNESS)
            draw_text(painter, button, text, to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT), font)
            if index == active:
                # the indicator marks the active tab at the edge of the bar next to the content
                if horizontal:
                    edge = _INDICATOR_THICKNESS
                    top = (
                        button.bottom() - edge
                        if int(number(self.obj_data.get("btn_pos"), 1)) == _BUTTONS_TOP
                        else button.top()
                    )
                    mark = QtCore.QRectF(button.left() + 5, top, button.width() - 10, edge)
                else:
                    mark = QtCore.QRectF(button.left(), button.top() + 5, _INDICATOR_THICKNESS, button.height() - 10)
                draw_box(
                    painter, mark, box_style(self, Part.INDICATOR, {**INDICATOR_DEFAULTS, "border_width": 0, "radius": 2})
                )
        super().paint(painter, option, widget)
