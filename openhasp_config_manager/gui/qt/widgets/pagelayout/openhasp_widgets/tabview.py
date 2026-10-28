from typing import Optional

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.tabs import tab_texts
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
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
# the indicator under the active tab is this far from the ends of the tab, and has these corners
_INDICATOR_MARGIN = 5
_INDICATOR_RADIUS = 2
# a pressed tab button: `#888` at this opacity over the bar (`tabview_btns` of lv_theme_hasp.c, computed, not measured)
_PRESSED_COLOR = "#888888"
_PRESSED_OPA = 127


class HaspTabviewItem(EditableWidget):
    """
    A container with a row (or column) of tab buttons at `btn_pos`: 0 none, 1 top, 2 bottom, 3 left, 4 right. The buttons are the
    `tab` objects that have the tabview as their `parentid`; `val` is the active one. Objects on a tab are not drawn inside of it.
    The height of the button row is `pad_top40` + `pad_bottom40` on top of the default.
    Touched, a tab button looks pressed (a gray overlay), and releasing it makes its tab the active one (`val`). Swiping the content
    and the 300 ms slide of the content are not shown: the objects on a tab are not drawn inside of it either.
    See https://www.openhasp.com/0.7.0/design/objects/tabview/
    """

    def button_rects(self):
        """:return: the rect of every tab button, in the order of the tabs"""
        area = self.button_area()
        tabs = self.tabs()
        if area.isEmpty() or not tabs:
            return []
        horizontal = area.width() >= area.height() and self.buttons_position in (_BUTTONS_TOP, _BUTTONS_BOTTOM)
        if horizontal:
            return [
                QtCore.QRectF(
                    area.left() + area.width() * index / len(tabs), area.top(), area.width() / len(tabs), area.height()
                )
                for index in range(len(tabs))
            ]
        return [
            QtCore.QRectF(area.left(), area.top() + _BUTTON_THICKNESS * index, area.width(), _BUTTON_THICKNESS)
            for index in range(len(tabs))
        ]

    def button_at(self, point) -> Optional[int]:
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        return next((index for index, rect in enumerate(self.button_rects()) if rect.contains(local)), None)

    def on_press(self, point):
        index = self.button_at(point)
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
            self.runtime.set(self.key, "val", index, self.obj_data)
            self.runtime_changed()
            self.follow_group(index, len(self.tabs()))

    @property
    def buttons_position(self) -> int:
        """:return: where the tab buttons are (`btn_pos`)"""
        return int(number(self.obj_data.get("btn_pos"), _BUTTONS_TOP))

    def tabs(self):
        return tab_texts(getattr(self.parent_widget, "objects", []), self.obj_data)

    def button_area(self) -> QtCore.QRectF:
        """:return: where the tab buttons are, an empty rect without buttons"""
        position = self.buttons_position
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
        horizontal = area.width() >= area.height() and self.buttons_position in (_BUTTONS_TOP, _BUTTONS_BOTTOM)
        # the tab buttons (part 4) are one bar
        draw_box(painter, area, box_style(self, Part.ITEMS, {"bg_color": _BAR_COLOR, "bg_opa": 255, "radius": 0}))
        active = int(number(self.data.get("val"), 0))
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE, Part.ITEMS))
        for index, text in enumerate(tabs):
            if horizontal:
                button = QtCore.QRectF(
                    area.left() + area.width() * index / len(tabs), area.top(), area.width() / len(tabs), area.height()
                )
            else:
                button = QtCore.QRectF(area.left(), area.top() + _BUTTON_THICKNESS * index, area.width(), _BUTTON_THICKNESS)
            if self.runtime.is_pressed(self.key) and self.runtime.pressed_part == index:
                overlay = QtGui.QColor(_PRESSED_COLOR)
                overlay.setAlpha(_PRESSED_OPA)
                painter.fillRect(button, overlay)
            draw_text(painter, button, text, to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT), font)
            if index == active:
                # the indicator marks the active tab at the edge of the bar next to the content
                if horizontal:
                    top = button.bottom() - _INDICATOR_THICKNESS if self.buttons_position == _BUTTONS_TOP else button.top()
                    mark = QtCore.QRectF(
                        button.left() + _INDICATOR_MARGIN, top, button.width() - 2 * _INDICATOR_MARGIN, _INDICATOR_THICKNESS
                    )
                else:
                    mark = QtCore.QRectF(
                        button.left(),
                        button.top() + _INDICATOR_MARGIN,
                        _INDICATOR_THICKNESS,
                        button.height() - 2 * _INDICATOR_MARGIN,
                    )
                draw_box(
                    painter,
                    mark,
                    box_style(self, Part.INDICATOR, {**INDICATOR_DEFAULTS, "border_width": 0, "radius": _INDICATOR_RADIUS}),
                )
        super().paint(painter, option, widget)
