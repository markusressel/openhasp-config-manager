"""
Scrolling and clicking a roller (LVGL v7.11, `lv_roller.c`). Qt-free: the widget animates and draws what this computes.

An offset is how far the rows are moved from where the selected option is in the middle, in pixels (positive: down).
"""

import math
from typing import Optional


# the time the rows take to snap to an option (`LV_ROLLER_DEF_ANIM_TIME`), the animation is linear
SNAP_TIME = 0.2


def settled_option(selected: int, offset: float, row: float, count: int, infinite: bool) -> int:
    """
    :param selected: the selected option before the drag, in a roller in infinite mode its index in the list of options
    :return: the option that is in the middle when the finger is let go (`LV_SIGNAL_DRAG_END`): the nearest to the middle, and
        the first or last if the rows were moved beyond them
    """
    index = math.floor(selected - offset / row + 0.5)
    if infinite:
        return index % count
    return min(max(index, 0), count - 1)


def clicked_option(
    selected: int, y: float, height: float, offset: float, row: float, count: int, infinite: bool
) -> Optional[int]:
    """
    :param y: where the finger is, relative to the top of the roller
    :param height: the height of the roller
    :return: the option on a row that was clicked (`release_handler`), None if there are no options
    """
    if count == 0:
        return None
    middle = height / 2 - row / 2
    index = selected + math.floor((y - middle - offset) / row)
    if infinite:
        return index % count
    return min(max(index, 0), count - 1)
