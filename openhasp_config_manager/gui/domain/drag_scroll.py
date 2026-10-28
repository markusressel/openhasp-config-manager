"""
Dragging and throwing what scrolls vertically (the rows of a roller, the open list of a dropdown), like LVGL v7.11 does it with the
scrollable of a page: `indev_drag` and `indev_drag_throw` of `lv_indev.c`, `scrl_reposition` of `lv_page.c`. Qt-free.

LVGL reads the touch every `READ_PERIOD` and does everything per read, in whole pixels, so the result depends on the reads: the
widget calls `read` with where the finger is at every read while it is down, and `throw_step` at every read after it was let go.
There is no elastic overscroll in LVGL v7: the scrollable stops at its ends.
"""

from openhasp_config_manager.gui.domain.interaction import DRAG_LIMIT
from openhasp_config_manager.gui.domain.touch_values import c_div

# how often the plate reads the touch (`LV_INDEV_DEF_READ_PERIOD` of lv_conf_v7.h), in seconds
READ_PERIOD = 0.02
# how much a throw slows down per read, in percent (`LV_INDEV_DEF_DRAG_THROW` of lv_conf_v7.h)
THROW_SLOWDOWN = 20


class DragScroll:
    """
    The position of something that a finger drags up and down, between `minimum` and `maximum` (e.g. how far the rows are moved).

    - The finger has to move `DRAG_LIMIT` pixels before it drags; then the position jumps by all of that at once (and, like LVGL, by
      the move of that read a second time) and follows the finger from then on.
    - While the finger moves, LVGL keeps a throw vector: the recent moves, the older ones fading. When the finger is let go after a drag,
      the position keeps moving by it, slower with every read, until it is 0 or the position is at an end: the drag ends
      (`LV_SIGNAL_DRAG_END`), which is when a roller snaps to an option.
    """

    def __init__(self, position: int, minimum: int, maximum: int):
        self.position = position
        self.minimum = minimum
        self.maximum = max(minimum, maximum)
        self._last = 0
        self._sum = 0
        self._limit_out = False
        self._throw = 0
        # the position was moved by a drag (`drag_in_prog`): the release is no click, and a drag end follows
        self.dragging = False
        self.throwing = False

    def _clamp(self, position: int) -> int:
        return min(max(position, self.minimum), self.maximum)

    def press(self, y: int):
        """The finger touches (the first read). A throw that was still going on ends."""
        self._last = y
        self._sum = 0
        self._limit_out = False
        self._throw = 0
        self.dragging = False
        self.throwing = False

    def read(self, y: int) -> bool:
        """
        A read while the finger is down at `y`.
        :return: whether the drag started with this read (LVGL: `LV_SIGNAL_DRAG_BEGIN`, e.g. a pressed row is not pressed anymore)
        """
        move = y - self._last
        self._last = y
        # `indev_pointer_proc`: the throw vector forgets 3/8 of itself and one pixel per read, and takes half of the move
        throw = (self._throw * 5) >> 3
        if throw < 0:
            throw += 1
        elif throw > 0:
            throw -= 1
        self._throw = throw + ((move * 4) >> 3)

        started = False
        if not self._limit_out:
            self._sum += move
            if abs(self._sum) >= DRAG_LIMIT:
                self._limit_out = True
                started = True
        if self._limit_out and move != 0:
            self.position = self._clamp(self.position + move + (self._sum if started else 0))
            self.dragging = True
        return started and self.dragging

    def release(self) -> bool:
        """
        The finger is let go (that read throws already, see `throw_step`).
        :return: whether the drag ended with it (a drag without a throw); False if there was no drag, or it goes on as a throw
        """
        if not self.dragging:
            return False
        self.throwing = True
        return not self.throw_step()

    def throw_step(self) -> bool:
        """
        A read after the finger was let go.
        :return: whether the throw goes on; False when it ended (the drag ended: `LV_SIGNAL_DRAG_END`)
        """
        if not self.throwing:
            return False
        self._throw = c_div(self._throw * (100 - THROW_SLOWDOWN), 100)
        before = self.position
        if self._throw != 0:
            self.position = self._clamp(self.position + self._throw)
        if self._throw == 0 or self.position == before:
            self._throw = 0
            self.throwing = False
            self.dragging = False
            return False
        return True

    def stop(self) -> bool:
        """
        A new touch stops a throw at once (`indev_proc_press` sets the throw vector to 0).
        :return: whether a drag ended with it
        """
        if not self.throwing:
            return False
        self._throw = 0
        self.throwing = False
        self.dragging = False
        return True
