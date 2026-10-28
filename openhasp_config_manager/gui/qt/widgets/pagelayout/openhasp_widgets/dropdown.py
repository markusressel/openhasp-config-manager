import dataclasses
from typing import Optional

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.dropdown_list import (
    PADDING_X,
    SCROLLBAR_RIGHT,
    SCROLLBAR_WIDTH,
    DropdownList,
    default_max_height,
    open_list,
    row_height,
)
from openhasp_config_manager.gui.domain.style_parts import Part, State
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding, resolve
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.checkbox import BULLET_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import INDICATOR_DEFAULTS, TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    line_lead,
    number,
    option_lines,
    plate_font,
    round_pen,
    selected_index,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.scrolling import ScrollDriver

_DEFAULTS = {
    **TRACK_DEFAULTS,
    "bg_color@4": INDICATOR_DEFAULTS["bg_color"],
    "bg_grad_color@4": INDICATOR_DEFAULTS["bg_grad_color"],
    # pressed: the box of the dropdown is styled like the bullet of a checkbox (`cb_bullet`)
    "bg_color@2": BULLET_DEFAULTS["bg_color@2"],
    "bg_grad_color@2": BULLET_DEFAULTS["bg_grad_color@2"],
}
# the list: dark like the box of the dropdown and without its style (measured: `bg_color` and `radius` of the object don't change it)
_LIST_DEFAULTS = {**TRACK_DEFAULTS}
# the selected row: the blue of the indicator with square corners, `COLOR_BTN_PR` at the top while it is pressed (`selected` in lv_theme_hasp.c)
_SELECTED_DEFAULTS = {**INDICATOR_DEFAULTS, "radius": 0, "bg_color@2": "#18BEFF", "text_color@2": "#FFFFFF"}
_SCROLLBAR_COLOR = "#8B9DA4"
# measured on a plate: the selected entry starts this far from the top left corner (the first line of a label does) and leaves room
# for the symbol on the right, which sits this far from the right edge and follows the size of the font
_TEXT_OFFSET = 6
_SYMBOL_RESERVE = 30
_SYMBOL_MARGIN = 7
# the symbol: a chevron that is a quarter of the font wide and half of that deep, drawn with a thin line
_SYMBOL_DEPTH = 0.5
_SYMBOL_LINE_WIDTH = 1.5
# measured: the symbol points down whatever `direction` says (`dd_open_direction`)
_SYMBOL_DIRECTION = (0, 1)


class _ThemeOnly:
    """Stands in for an object without style properties, for the parts of a dropdown that its properties don't style."""

    state = State.DEFAULT

    def own_style(self, name: str, part: Part, state: State):
        return None


class HaspDropdownItem(EditableWidget):
    """
    A closed dropdown: the selected entry of `options` (by `val`) and an arrow. The open list is not drawn.
    Touched (see `RuntimeState`), the list opens: below the dropdown, or above it if there is no room (`direction` sets another side),
    cut at `max_height` and the screen, scrolled to the selected row, with a scrollbar if it doesn't fit. A row that is touched and
    released is the new `val` and closes the list. A finger that drags the list scrolls it (and throws it, like LVGL), selecting nothing.
    See https://www.openhasp.com/0.7.0/design/objects/dropdown/
    """

    def __init__(self, *args, **kwargs):
        self._painted_bounds: Optional[QtCore.QRectF] = None
        # where the first row of the open list is after dragging it, None while it is where it opened
        self._list_scroll: Optional[int] = None
        # the finger pressed the open list (not the box of the dropdown)
        self._on_list = False
        super().__init__(*args, **kwargs)
        self._scroll = ScrollDriver(self, moved=self._scroll_list, drag_began=self._unpress_row, drag_ended=lambda: None)

    @property
    def is_open(self) -> bool:
        return self.runtime.open_dropdown == self.key

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", DEFAULT_FONT_SIZE))

    @property
    def obj_h(self) -> int:
        # measured, and `LV_SIGNAL_STYLE_CHG` of `lv_dropdown.c`: a font sets the height to what fits one row (`h` is ignored)
        if self.obj_data.get("text_font") is not None:
            return row_height(self.font.pixelSize()) - 1
        return super().obj_h

    def open_layout(self) -> Optional[DropdownList]:
        """:return: the open list (in the coordinates of the plate), None if the dropdown is closed"""
        if not self.is_open:
            # however the list was closed (a row, a touch elsewhere, Reset): it opens scrolled to the selected row again
            self._list_scroll = None
            return None
        options = option_lines(self.obj_data.get("options"))
        font = self.font
        metrics = QtGui.QFontMetricsF(font)
        screen = self.scene().sceneRect()
        screen_size = (round(screen.width()), round(screen.height()))
        data = self.data
        opened = open_list(
            (self.obj_x, self.obj_y, self.obj_w, self.obj_h),
            len(options),
            row_height(font.pixelSize()),
            max((metrics.horizontalAdvance(option) for option in options), default=0),
            int(number(data.get("direction"), 0)),
            int(number(data.get("max_height"), default_max_height(screen_size[1]))),
            selected_index(data),
            screen_size,
        )
        return opened if self._list_scroll is None else dataclasses.replace(opened, scroll=self._list_scroll)

    def _local_list_rect(self) -> Optional[QtCore.QRectF]:
        opened = self.open_layout()
        return None if opened is None else QtCore.QRectF(opened.x - self.obj_x, opened.y - self.obj_y, opened.w, opened.h)

    def boundingRect(self) -> QtCore.QRectF:
        rect = super().boundingRect()
        opened = self._local_list_rect()
        return rect if opened is None else rect.united(opened.adjusted(-1, -1, 1, 1))

    def _update_hidden(self):
        super()._update_hidden()
        # the list is above the other objects
        self.setZValue(1 if self.is_open else 0)

    def _invalidate_painted(self):
        """What was drawn before (the list that is closed now) has to be drawn again as well."""
        if self._painted_bounds is not None and self.scene() is not None:
            self.scene().update(self.mapRectToScene(self._painted_bounds))

    def runtime_changed(self):
        self._invalidate_painted()
        super().runtime_changed()

    def refresh(self):
        self._invalidate_painted()
        super().refresh()

    def hit(self, local: QtCore.QPointF) -> bool:
        opened = self._local_list_rect()
        return super().hit(local) or (opened is not None and opened.contains(local))

    def _row_at(self, point) -> Optional[int]:
        """:return: the row of the open list at a point of the plate, None if the point is not on the list"""
        opened = self.open_layout()
        return opened.row_at(point[1]) if opened is not None and opened.contains(point) else None

    @property
    def keeps_press(self) -> bool:
        # the scrollable of the list is protected against losing the press (`lv_page`), the box of the dropdown is not
        return self._on_list

    def _scroll_list(self, position: int):
        self._list_scroll = position
        self.runtime_changed()

    def _unpress_row(self):
        """The finger drags the list (`LV_SIGNAL_DRAG_BEGIN`): the row it pressed is not pressed anymore."""
        self.runtime.pressed_row = None
        self.runtime_changed()

    def on_press(self, point):
        self._scroll.stop_throw()
        row = self._row_at(point)
        self._on_list = row is not None
        self.runtime.pressed_row = row
        self.set_pressed(True, part=None if row is None else 1)
        opened = self.open_layout()
        if row is not None and opened is not None:
            self._scroll.press(point[1], opened.scroll, min(opened.h - opened.content_height, 0), 0)

    def on_pressing(self, point):
        # the pressed row stays the one that was pressed (`page_press_handler`), until the finger drags the list
        if self._on_list:
            self._scroll.move(point[1])

    def on_release(self, point, short_click: bool):
        row = self._row_at(point)
        pressed_row, self.runtime.pressed_row = self.runtime.pressed_row, None
        dragged = self._scroll.dragging
        self._on_list = False
        self._scroll.release()
        self.set_pressed(False)
        if dragged:
            # `page_release_handler` doesn't run while dragging: nothing is selected, the list stays open
            return
        if pressed_row is not None and row is not None:
            # `page_release_handler`: the row under the finger is selected, and the list closes
            self.runtime.set(self.key, "val", row, self.obj_data)
            self.close_list()
            self.follow_group(row, len(option_lines(self.obj_data.get("options"))))
        elif pressed_row is None:
            # `LV_SIGNAL_RELEASED` of the dropdown itself
            self.runtime.open_dropdown = None if self.is_open else self.key
            self.runtime_changed()

    def on_press_lost(self):
        self._on_list = False
        self._scroll.cancel()
        self.runtime.pressed_row = None
        self.set_pressed(False)

    def close_list(self):
        if self.is_open:
            self.runtime.open_dropdown = None
        self._scroll.cancel()
        self.runtime_changed()

    def _draw_list(self, painter: QtGui.QPainter, opened: DropdownList):
        """The list over the other objects: the background, the rows (the selected and the pressed one highlighted) and the scrollbar."""
        painter.save()
        origin = QtCore.QPointF(opened.x - self.obj_x, opened.y - self.obj_y)
        rect = QtCore.QRectF(origin, QtCore.QSizeF(opened.w, opened.h))
        list_style = box_style(_ThemeOnly(), Part.MAIN, _LIST_DEFAULTS)
        draw_box(painter, rect, list_style)

        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, list_style.radius, list_style.radius)
        painter.setClipPath(clip)
        font = self.font
        item_color = to_color(self.style("text_color", None, Part.ITEMS), DEFAULT_TEXT)
        selected = selected_index(self.data)
        pressed = self.runtime.pressed_row
        for index, entry in enumerate(option_lines(self.obj_data.get("options"))):
            row = QtCore.QRectF(rect.left(), rect.top() + opened.row_top(index), opened.w, opened.row)
            if row.bottom() < rect.top() or row.top() > rect.bottom():
                continue
            color = item_color
            for state, is_marked in ((State.DEFAULT, index == selected), (State.PRESSED, index == pressed)):
                if is_marked:
                    draw_box(painter, row, box_style(self, Part.SELECTED, _SELECTED_DEFAULTS, state))
                    color = to_color(resolve(self, "text_color", Part.SELECTED, _SELECTED_DEFAULTS, state), DEFAULT_TEXT)
            draw_text(painter, row.adjusted(PADDING_X, 0, -PADDING_X, 0), entry, color, font, "left")
        painter.setClipping(False)
        draw_box(painter, rect, dataclasses.replace(list_style, bg_opa=0, shadow_width=0))

        if opened.scrolls:
            top, length = opened.thumb()
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(_SCROLLBAR_COLOR))
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            thumb = QtCore.QRectF(rect.right() - SCROLLBAR_RIGHT - SCROLLBAR_WIDTH, rect.top() + top, SCROLLBAR_WIDTH, length)
            painter.drawRoundedRect(thumb, SCROLLBAR_WIDTH / 2, SCROLLBAR_WIDTH / 2)
        painter.restore()

    @property
    def selected_text(self) -> str:
        options = option_lines(self.obj_data.get("options"))
        index = selected_index(self.data)
        return options[index] if 0 <= index < len(options) else ""

    def paint(self, painter, option, widget=None):
        # the box is a track, a disabled dropdown has the blue of the indicator
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, _DEFAULTS))

        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        _, _, right, _ = padding(self, Part.MAIN)
        left, top = (number(self.style(f"pad_{side}", _TEXT_OFFSET), _TEXT_OFFSET) for side in ("left", "top"))
        font = plate_font(self.style("text_font", DEFAULT_FONT_SIZE))
        draw_text(
            painter,
            self.obj_rect.adjusted(left, top, -(_SYMBOL_RESERVE + right), 0),
            self.selected_text,
            color,
            font,
            "left",
            "top",
        )

        size = font.pixelSize()
        center = QtCore.QPointF(
            self.obj_w - _SYMBOL_MARGIN - size / 2 - right, top + (QtGui.QFontMetricsF(font).height() + line_lead(font)) / 2
        )
        dx, dy = _SYMBOL_DIRECTION
        tip = center + QtCore.QPointF(dx, dy) * size / 4 * _SYMBOL_DEPTH
        back = center - QtCore.QPointF(dx, dy) * size / 4 * _SYMBOL_DEPTH
        side = QtCore.QPointF(-dy, dx) * size / 4
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(round_pen(color, _SYMBOL_LINE_WIDTH))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QtGui.QPolygonF([back + side, tip, back - side]))
        painter.restore()
        opened = self.open_layout()
        if opened is not None:
            self._draw_list(painter, opened)
        self._painted_bounds = self.boundingRect()
        super().paint(painter, option, widget)
