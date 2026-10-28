"""
Swiping the content of a tabview to another tab, like LVGL v7.11 does it: `indev_drag` of `lv_indev.c` and `tabview_scrl_signal` of
`lv_tabview.c`. Qt-free.

The finger presses the page of a tab. Its first drag moves that page, which can't move when its objects fit, and so it hands the drag on to
the content of the tabview (scroll propagation): that read moves nothing, the following ones move the content sideways. Whether the drag
goes sideways is decided when the finger has moved `DRAG_LIMIT` pixels. When the finger is let go, the move of the last read predicts how
far the content would still go, and the tab whose page would be over the middle of the tabview becomes the active one.
"""

from typing import Optional

from openhasp_config_manager.gui.domain.drag_scroll import THROW_SLOWDOWN
from openhasp_config_manager.gui.domain.interaction import DRAG_LIMIT
from openhasp_config_manager.gui.domain.touch_values import c_div


def predicted_move(move: int) -> int:
    """:return: how far a throw with the move of the last read would still go: that move, slower with every read"""
    result = 0
    while move != 0:
        result += move
        move = c_div(move * (100 - THROW_SLOWDOWN), 100)
    return result


class TabSwipe:
    """A finger on the content of a tabview with `count` tabs, of which `active` is shown; a tab page is `width` wide."""

    def __init__(self, active: int, count: int, width: int):
        self.active = active
        self.count = count
        self.width = width
        # how far the content is moved sideways from where the active tab is shown (positive: to the right)
        self.shift = 0
        self._last = (0, 0)
        self._sum = (0, 0)
        self._move = 0
        self._limit_out = False
        self._sideways = False

    @property
    def dragging(self) -> bool:
        return self._limit_out

    def press(self, x: int, y: int):
        self._last = (x, y)

    def read(self, x: int, y: int):
        """A read while the finger is down at (`x`, `y`)."""
        move_x, move_y = x - self._last[0], y - self._last[1]
        self._last = (x, y)
        self._move = move_x
        if not self._limit_out:
            self._sum = (self._sum[0] + move_x, self._sum[1] + move_y)
            if abs(self._sum[0]) >= DRAG_LIMIT or abs(self._sum[1]) >= DRAG_LIMIT:
                self._limit_out = True
                self._sideways = abs(self._sum[0]) > abs(self._sum[1])
                # the page of the tab takes this read, and hands the drag on to the content
                return
        if self._limit_out and self._sideways and move_x != 0:
            # `scrl_reposition`: the first and the last tab can't be moved away from the edges
            lowest = -(self.count - 1 - self.active) * self.width
            highest = self.active * self.width
            self.shift = min(max(self.shift + move_x, lowest), highest)

    def release(self, offset: int, tabview_width: int) -> Optional[int]:
        """
        The finger is let go (`LV_SIGNAL_DRAG_THROW_BEGIN`).
        :param offset: where the content starts in the tabview (the width of the tab buttons on the left, else 0)
        :return: the tab that becomes the active one, None if the finger didn't drag
        """
        if not self._limit_out:
            return None
        # the move of the last read counts, sideways or not
        page_left = offset + self.shift + predicted_move(self._move)
        page_right = page_left + tabview_width
        threshold = tabview_width // 2
        tab = self.active
        if page_left > threshold:
            tab -= 1
        elif page_right < threshold:
            tab += 1
        return min(max(tab, 0), self.count - 1)
