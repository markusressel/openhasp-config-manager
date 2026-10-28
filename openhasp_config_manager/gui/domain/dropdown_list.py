"""
The open list of a dropdown, as `lv_dropdown_open` lays it out (LVGL v7.11). Qt-free: the widget draws what this computes.

Measured on a plate (`tests/resources/preview_device/screenshots/dd_open_*.png`): a row is as high as a row of a roller, the
list of three rows is 134 pixels high (rows * height - 1), the text starts 6 pixels from the left edge of the list, the scrollbar is
4 pixels wide and sits 4 pixels from the right edge.
"""

import math
from dataclasses import dataclass
from typing import Tuple

# LVGL: `lv_dropdown_dir_t`
DIR_DOWN, DIR_UP, DIR_LEFT, DIR_RIGHT = 0, 1, 2, 3

# the space between the text and the left and right edge of the list
PADDING_X = 6
# the scrollbar: width, distance to the right edge and the space above and below it
SCROLLBAR_WIDTH = 4
SCROLLBAR_RIGHT = 4
SCROLLBAR_MARGIN = 3
# the thumb is a bit shorter than the share of the list that is visible
SCROLLBAR_SHRINK = 5

# measured: the height of a row is this many pixels per pixel of the font and this many on top (45 for font 24, 36 for 16, 31 for 12)
_ROW_PER_FONT_PIXEL = 1.167
_ROW_EXTRA = 17


def row_height(font_pixels: int) -> int:
    """:return: the height of a row of a dropdown list (the font and the `text_line_space` of the theme)"""
    return round(font_pixels * _ROW_PER_FONT_PIXEL + _ROW_EXTRA)


def default_max_height(screen_height: int) -> int:
    """:return: `max_height` of a dropdown that doesn't set it (`lv_dropdown_create`)"""
    return 3 * screen_height // 4


@dataclass(frozen=True)
class DropdownList:
    """An open list: where it is on the screen, and how its rows lie in it."""

    x: int
    y: int
    w: int
    h: int
    # the direction the list really opens in (the one of the dropdown, or the other one if there is no room)
    direction: int
    row: int
    count: int
    # where the first row is relative to the top of the list: 0, or negative if the list is scrolled
    scroll: int

    @property
    def content_height(self) -> int:
        return content_height(self.count, self.row)

    @property
    def scrolls(self) -> bool:
        return self.content_height > self.h

    def contains(self, point: Tuple[float, float]) -> bool:
        return self.x <= point[0] < self.x + self.w and self.y <= point[1] < self.y + self.h

    def row_top(self, index: int) -> int:
        """:return: the top of a row, relative to the top of the list"""
        return self.scroll + index * self.row

    def row_at(self, y: float) -> int:
        """:return: the row at a y of the screen (`get_id_on_point`: the first and last row take what is beyond the list)"""
        return min(max(int((y - self.y - self.scroll) // self.row), 0), self.count - 1)

    def thumb(self) -> Tuple[int, int]:
        """:return: top (relative to the top of the list) and length of the thumb of the scrollbar"""
        length = max(round(self.h * self.h / self.content_height) - SCROLLBAR_SHRINK, 1)
        track = self.h - 2 * SCROLLBAR_MARGIN
        hidden = self.content_height - self.h
        share = -self.scroll / hidden if hidden else 0
        return SCROLLBAR_MARGIN + round((track - length) * share), length


def content_height(count: int, row: int) -> int:
    """:return: the height of all rows (one pixel less than their heights add up to, measured)"""
    return count * row - 1


def scroll_to(selected: int, row: int, count: int, height: int) -> int:
    """:return: where the first row is when the list opens (`position_to_selected`): the selected row in the middle, if possible"""
    scroll = (height - row) // 2 - selected * row
    return min(max(scroll, height - content_height(count, row)), 0)


def open_list(
    box: Tuple[int, int, int, int],
    count: int,
    row: int,
    widest: float,
    direction: int,
    max_height: int,
    selected: int,
    screen: Tuple[int, int],
) -> DropdownList:
    """
    :param box: x, y, width and height of the dropdown
    :param count: the number of options
    :param row: the height of a row
    :param widest: the width of the widest option
    :param direction: `direction` of the dropdown (`DIR_*`)
    :param max_height: `max_height` of the dropdown
    :param selected: the selected option, which the list is scrolled to
    :param screen: width and height of the screen
    """
    x, y, w, h = box
    screen_w, screen_h = screen
    # LVGL areas include their last pixel
    last = y + h - 1
    fit = content_height(count, row)
    height = min(fit, max_height)
    actual = direction
    if direction == DIR_DOWN and last + height > screen_h:
        # no room below: above if there is more of it, else as far as the screen goes
        if y > screen_h - last:
            actual, height = DIR_UP, y
        else:
            height = screen_h - last
    elif direction == DIR_UP and y - height < 0:
        if y < screen_h - last:
            actual, height = DIR_DOWN, screen_h - last
        else:
            height = y
    height = min(height, fit, max_height)

    text_width = math.ceil(widest) + 2 * PADDING_X
    # above and below the list is as wide as the dropdown, or wider if the options need it
    width = max(w, text_width) if direction in (DIR_DOWN, DIR_UP) else text_width

    if actual == DIR_DOWN:
        left, top = x, y + h
    elif actual == DIR_UP:
        left, top = x, y - height
    elif actual == DIR_LEFT:
        left, top = x - width, y
    else:
        left, top = x + w, y
    if direction in (DIR_LEFT, DIR_RIGHT) and top + height > screen_h:
        top -= top + height - screen_h
    return DropdownList(left, top, width, height, actual, row, count, scroll_to(selected, row, count, height))
