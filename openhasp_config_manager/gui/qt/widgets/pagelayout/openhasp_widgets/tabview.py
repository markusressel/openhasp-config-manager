from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.tabs import tab_texts
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TEXT,
    DEFAULT_TRACK,
    draw_text,
    number,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_BUTTONS_TOP, _BUTTONS_BOTTOM, _BUTTONS_LEFT, _BUTTONS_RIGHT = 1, 2, 3, 4
_BUTTON_THICKNESS = 40
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
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(to_color(self.style("bg_color"), DEFAULT_TRACK))
        painter.setPen(QtGui.QPen(to_color(self.style("border_color"), "#808080"), number(self.style("border_width", 1), 1)))
        painter.drawRect(self.obj_rect)

        area = self.button_area()
        tabs = self.tabs()
        if area.isEmpty() or not tabs:
            return super().paint(painter, option, widget)
        horizontal = area.width() >= area.height() and int(number(self.obj_data.get("btn_pos"), 1)) in (
            _BUTTONS_TOP,
            _BUTTONS_BOTTOM,
        )
        painter.setBrush(QtGui.QColor(0, 0, 0, 60))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRect(area)
        active = int(number(self.obj_data.get("val"), 0))
        font = plate_font(self.style("text_font", 25, Part.ITEMS))
        for index, text in enumerate(tabs):
            if horizontal:
                button = QtCore.QRectF(
                    area.left() + area.width() * index / len(tabs), area.top(), area.width() / len(tabs), area.height()
                )
            else:
                button = QtCore.QRectF(area.left(), area.top() + _BUTTON_THICKNESS * index, area.width(), _BUTTON_THICKNESS)
            on = index == active
            draw_text(
                painter,
                button,
                text,
                to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_ACCENT if on else DEFAULT_TEXT),
                font,
            )
            if on:
                painter.setPen(QtGui.QPen(to_color(self.style("bg_color", DEFAULT_ACCENT, Part.INDICATOR), DEFAULT_ACCENT), 3))
                edge = button.bottomLeft(), button.bottomRight()
                painter.drawLine(*edge)
        super().paint(painter, option, widget)
