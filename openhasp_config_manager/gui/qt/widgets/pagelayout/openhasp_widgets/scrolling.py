from typing import Callable, Optional

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.drag_scroll import READ_PERIOD, DragScroll


class ScrollDriver(QtCore.QObject):
    """
    Reads the finger for a `DragScroll` like the plate does: once when it touches, then every `READ_PERIOD` while it is down, and
    every `READ_PERIOD` after it was let go while the throw goes on. Mouse events only say where the finger is.
    """

    def __init__(
        self,
        parent: QtCore.QObject,
        moved: Callable[[int], None],
        drag_began: Callable[[], None],
        drag_ended: Callable[[], None],
    ):
        """
        :param moved: the position changed (dragged or thrown)
        :param drag_began: the finger moved far enough to drag (e.g. a pressed row is not pressed anymore)
        :param drag_ended: the drag is over (after the throw), e.g. a roller snaps to an option
        """
        super().__init__(parent)
        self._moved = moved
        self._drag_began = drag_began
        self._drag_ended = drag_ended
        self.scroll: Optional[DragScroll] = None
        self._finger: Optional[int] = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(round(READ_PERIOD * 1000))
        self._timer.timeout.connect(self.tick)

    @property
    def dragging(self) -> bool:
        return self.scroll is not None and self.scroll.dragging

    def stop_throw(self):
        """A new touch stops a throw that is still going on: the drag ends there."""
        if self.scroll is not None and self.scroll.stop():
            self._timer.stop()
            self._drag_ended()

    def press(self, y: float, position: int, minimum: int, maximum: int):
        self.stop_throw()
        self.scroll = DragScroll(position, minimum, maximum)
        self.scroll.press(round(y))
        self._finger = round(y)
        self._timer.start()

    def move(self, y: float):
        """Where the finger is now: the next read takes it."""
        self._finger = round(y)

    def release(self):
        """The finger is let go: the drag ends now, or after the throw."""
        scroll = self.scroll
        self._finger = None
        if scroll is None:
            self._timer.stop()
            return
        before = scroll.position
        if not scroll.dragging:
            self._timer.stop()
            return
        ended = scroll.release()
        if scroll.position != before:
            self._moved(scroll.position)
        if ended:
            self._timer.stop()
            self._drag_ended()

    def cancel(self):
        """Forget the finger and the throw (the press was lost, or the object is reset)."""
        self._timer.stop()
        self._finger = None
        self.scroll = None

    def tick(self):
        """One read of the plate."""
        scroll = self.scroll
        if scroll is None:
            self._timer.stop()
            return
        before = scroll.position
        if self._finger is not None:
            if scroll.read(self._finger):
                self._drag_began()
            if scroll.position != before:
                self._moved(scroll.position)
            return
        going_on = scroll.throw_step()
        if scroll.position != before:
            self._moved(scroll.position)
        if not going_on:
            self._timer.stop()
            self._drag_ended()

    def finish(self):
        """Let a throw run to its end at once (tests don't wait for time)."""
        while self.scroll is not None and self._finger is None and self.scroll.throwing:
            self.tick()
