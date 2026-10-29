from typing import Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from openhasp_config_manager.gui.domain.drag_scroll import READ_PERIOD
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.domain.tab_swipe import TabSwipe
from openhasp_config_manager.gui.domain.tabs import tab_objects, tab_texts
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
# the time the indicator takes to move to another tab (`LV_TABVIEW_DEF_ANIM_TIME`), in ms, the animation is linear
DEFAULT_ANIM_TIME = 300


class HaspTabviewItem(EditableWidget):
    """
    A container with a row (or column) of tab buttons at `btn_pos`: 0 none, 1 top, 2 bottom, 3 left, 4 right. The buttons are the
    `tab` objects that have the tabview as their `parentid`; `val` is the active one. The objects on a tab (their `parentid` is the tab) are drawn on its page, the content area,
    only those of the active tab, clipped to it, with `x`/`y` relative to it (a tab is an `lv_page`, `lv_tabview_add_tab`; its
    scrollable has no offset on the left and top, so its padding doesn't move them).
    The height of the button row is `pad_top40` + `pad_bottom40` on top of the default.
    Touched, a tab button looks pressed (a gray overlay), and releasing it makes its tab the active one (`val`). Swiping the content
    sideways past the middle (or flicking it) makes the tab next to it the active one. The indicator moves to the active tab in
    `anim_time` (300 ms by default, linear). The content itself is not drawn moving: the page of the active tab is shown at once.
    See https://www.openhasp.com/0.7.0/design/objects/tabview/
    """

    def __init__(self, *args, **kwargs):
        self._anim = None
        self._swipe: Optional[TabSwipe] = None
        self._finger = None
        # the pages of the tabs that have objects on them, by the id of their tab
        self._pages: Dict[int, QtWidgets.QGraphicsRectItem] = {}
        super().__init__(*args, **kwargs)
        # the plate reads the finger every `READ_PERIOD` while it swipes, mouse events only say where it is
        self._swipe_timer = QtCore.QTimer(self)
        self._swipe_timer.setInterval(round(READ_PERIOD * 1000))
        self._swipe_timer.timeout.connect(self.read_swipe)

    @property
    def keeps_press(self) -> bool:
        # the content is dragged (`drag_in_prog`): the finger can leave the tabview
        return self._swipe is not None

    @property
    def indicator_position(self) -> float:
        """:return: which tab the indicator is at: the active one, in between while it moves"""
        if self._anim is not None:
            return float(self._anim.currentValue())
        return float(number(self.data.get("val"), 0))

    def finish_animation(self):
        """Let the indicator arrive at once (also when tests don't wait for time)."""
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
            self.update()

    def _activate(self, index: int):
        """`lv_tabview_set_tab_act` with an animation: the indicator moves from where it is to the tab."""
        start = self.indicator_position
        self.finish_animation()
        self.runtime.set(self.key, "val", index, self.obj_data)
        duration = int(number(self.data.get("anim_time"), DEFAULT_ANIM_TIME))
        if duration > 0 and start != index:
            animation = QtCore.QVariantAnimation(self)
            animation.setStartValue(start)
            animation.setEndValue(float(index))
            animation.setDuration(duration)
            animation.valueChanged.connect(self.update)
            animation.finished.connect(self.finish_animation)
            self._anim = animation
            animation.start()
        self.runtime_changed()
        self.follow_group(index, len(self.tabs()))

    def content_area(self) -> QtCore.QRectF:
        """:return: where the pages of the tabs are"""
        rect, buttons = self.obj_rect, self.button_area()
        position = self.buttons_position
        if buttons.isEmpty():
            return rect
        if position == _BUTTONS_TOP:
            return rect.adjusted(0, buttons.height(), 0, 0)
        if position == _BUTTONS_BOTTOM:
            return rect.adjusted(0, 0, 0, -buttons.height())
        if position == _BUTTONS_LEFT:
            return rect.adjusted(buttons.width(), 0, 0, 0)
        return rect.adjusted(0, 0, -buttons.width(), 0)

    def tab_page(self, tab: Dict) -> QtWidgets.QGraphicsRectItem:
        """:return: the page of one of the tabs, the parent of the items of the objects on it (created when first asked for)"""
        page = self._pages.get(tab.get("id"))
        if page is None:
            page = QtWidgets.QGraphicsRectItem(parent=self)
            page.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
            page.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
            # clicks beside the objects go to the tabview
            page.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            self._pages[tab.get("id")] = page
            self._update_pages()
        return page

    def _update_pages(self):
        """Place the pages on the content area, and show only the one of the active tab."""
        content = self.content_area()
        ids = [tab.get("id") for tab in self.tab_objects()]
        active = min(int(number(self.data.get("val"), 0)), len(ids) - 1)
        for tab_id, page in self._pages.items():
            page.setPos(content.topLeft())
            page.setRect(0, 0, content.width(), content.height())
            page.setVisible(tab_id in ids and ids.index(tab_id) == active)

    def _on_data_changed(self):
        super()._on_data_changed()
        self._update_pages()

    def runtime_changed(self):
        super().runtime_changed()
        self._update_pages()

    def read_swipe(self):
        """One read of the plate while the finger swipes."""
        if self._swipe is None or self._finger is None:
            self._swipe_timer.stop()
            return
        self._swipe.read(*self._finger)

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
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        tabs = len(self.tabs())
        if index is None and tabs and self.content_area().contains(local):
            # a page of a tab is pressed
            self._finger = (round(local.x()), round(local.y()))
            self._swipe = TabSwipe(
                min(int(number(self.data.get("val"), 0)), tabs - 1), tabs, round(self.content_area().width())
            )
            self._swipe.press(*self._finger)
            self._swipe_timer.start()

    def on_pressing(self, point):
        if self._swipe is not None:
            local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
            self._finger = (round(local.x()), round(local.y()))
            return
        index = self.button_at(point)
        part = -1 if index is None else index
        if self.runtime.is_pressed(self.key) and part != self.runtime.pressed_part:
            self.runtime.pressed_part = part
            self.runtime_changed()

    def on_release(self, point, short_click: bool):
        index = self.runtime.pressed_part
        self.set_pressed(False)
        swipe = self._swipe
        if swipe is not None:
            self._cancel_swipe()
            tab = swipe.release(round(self.content_area().left()), round(self.obj_w))
            if tab is not None:
                self._activate(tab)
            return
        if index is not None and index >= 0 and self.button_at(point) == index:
            self._activate(index)

    def _cancel_swipe(self):
        self._swipe_timer.stop()
        self._swipe = None
        self._finger = None

    def on_press_lost(self):
        self._cancel_swipe()
        super().on_press_lost()

    @property
    def buttons_position(self) -> int:
        """:return: where the tab buttons are (`btn_pos`)"""
        return int(number(self.obj_data.get("btn_pos"), _BUTTONS_TOP))

    def tabs(self):
        return tab_texts(getattr(self.parent_widget, "objects", []), self.obj_data)

    def tab_objects(self):
        return tab_objects(getattr(self.parent_widget, "objects", []), self.obj_data)

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
        indicator = self.indicator_position
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE, Part.ITEMS))
        buttons = self.button_rects()
        for index, (text, button) in enumerate(zip(tabs, buttons)):
            if self.runtime.is_pressed(self.key) and self.runtime.pressed_part == index:
                overlay = QtGui.QColor(_PRESSED_COLOR)
                overlay.setAlpha(_PRESSED_OPA)
                painter.fillRect(button, overlay)
            draw_text(painter, button, text, to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT), font)
        # the indicator marks the active tab at the edge of the bar next to the content, and moves between the tabs
        first = buttons[0]
        if horizontal:
            left = first.left() + first.width() * indicator
            top = first.bottom() - _INDICATOR_THICKNESS if self.buttons_position == _BUTTONS_TOP else first.top()
            mark = QtCore.QRectF(left + _INDICATOR_MARGIN, top, first.width() - 2 * _INDICATOR_MARGIN, _INDICATOR_THICKNESS)
        else:
            top = first.top() + first.height() * indicator
            mark = QtCore.QRectF(
                first.left(), top + _INDICATOR_MARGIN, _INDICATOR_THICKNESS, first.height() - 2 * _INDICATOR_MARGIN
            )
        draw_box(
            painter,
            mark,
            box_style(self, Part.INDICATOR, {**INDICATOR_DEFAULTS, "border_width": 0, "radius": _INDICATOR_RADIUS}),
        )
        super().paint(painter, option, widget)
