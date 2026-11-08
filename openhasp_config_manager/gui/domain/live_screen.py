"""
When the *Live device* view takes a screenshot of a plate (Qt-free, driven by the time it is given).

A screenshot is slow on an ESP32 and keeps the plate busy, so the view can't show the plate in real time. It takes one
  - every `interval` seconds (none if 0),
  - shortly after the screen changed (`screen_changed`): a deploy, *Restore plate*, *Live preview* sending changes, a command
    or a page change. Changes in a row wait until they have been quiet for the delay of their kind (typing into a property
    sends a change per keystroke), but not longer than `MAX_CHANGE_WAIT` after the first of them,
  - when the user asks for one (`refresh`),
only while the view is shown and the plate can be reached (`set_visible`, `set_reachable`). One screenshot of a plate runs at a
time: what is asked for meanwhile becomes one screenshot after it. After a failure the next one waits longer and longer
(`backoff_delay`), except one the user asks for.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from openhasp_config_manager.gui.domain.connection import LinkState

# the default interval, and those the view offers (seconds, 0: only after changes and when asked for)
DEFAULT_INTERVAL = 30
INTERVALS = (0, 10, 30, 60, 300)

# a series of changes is shown at the latest this long after its first one, also if it goes on (e.g. dragging with Live preview)
MAX_CHANGE_WAIT = 10.0

# the wait after the first failure in a row, doubled for each further one up to the longest
BACKOFF_START = 15.0
BACKOFF_MAX = 600.0


class ScreenChange(Enum):
    """What changed the screen of a plate, with the time it takes until it shows it (seconds)."""

    # Live preview sent changes of the draft: again and again while typing or dragging
    LIVE_PREVIEW = 2.0
    # a command (e.g. a page change through the buttons on the preview) or the plate reported another page
    COMMAND = 1.5
    # Live preview sent a whole page
    PAGE_SENT = 1.5
    # the plate builds its pages again from its files (Restore plate, after a deploy)
    RESTORED = 3.0
    # the plate is back (e.g. after a restart)
    RECONNECTED = 3.0

    @property
    def delay(self) -> float:
        return self.value


def reachable(link: LinkState) -> bool:
    """
    :return: whether a screenshot of a plate can be tried. Not while it is offline (its LWT), nor before the state of the
        connection is known. A screenshot goes over HTTP, so an unreachable MQTT broker doesn't stop it (failures back off).
    """
    return link not in (LinkState.NO_DEVICE, LinkState.CONNECTING, LinkState.PLATE_OFFLINE)


def backoff_delay(failures: int) -> float:
    """:return: how long to wait after `failures` failed screenshots in a row (0 without one)"""
    if failures <= 0:
        return 0.0
    return min(BACKOFF_START * 2 ** (failures - 1), BACKOFF_MAX)


@dataclass(frozen=True)
class ScreenshotState:
    """What the view shows about the screenshots of a plate, besides the image."""

    running: bool
    # why no screenshot is taken now (None if they are): "hidden", "unreachable"
    paused: Optional[str]
    # the error of the last screenshot, None if it worked (or there was none yet)
    error: Optional[str]
    failures: int
    # when the next one is taken, None if none is planned
    next_at: Optional[float]
    # when the last one that worked was finished, None before the first
    updated_at: Optional[float]


class ScreenshotScheduler:
    """
    Decides when to take a screenshot of one plate. The caller asks `poll` whether to start one now (at the times
    `next_wakeup` says, and after each call that may change it), takes it and reports the end (`succeeded`, `failed`).
    All times are seconds of a monotonic clock, as the caller gives them.
    """

    def __init__(self, interval: float = DEFAULT_INTERVAL):
        self._interval = interval
        self._visible = False
        self._reachable = False
        self._running = False
        # the end of the last screenshot (worked or not), None before the first
        self._finished_at: Optional[float] = None
        self._updated_at: Optional[float] = None
        # a screenshot because the screen changed, at this time; when the first of these changes was
        self._change_due: Optional[float] = None
        self._first_change: Optional[float] = None
        # the user asked for one: right away, also during a backoff
        self._manual = False
        self._failures = 0
        self._error: Optional[str] = None

    # --- what the caller reports ---

    @property
    def interval(self) -> float:
        return self._interval

    def set_interval(self, seconds: float):
        """:param seconds: the time between two screenshots, 0 for none (only after changes and when asked for)"""
        self._interval = seconds

    def set_visible(self, visible: bool):
        """Whether the view shows this plate (its dock is shown and not behind another one, its tab is the active one)."""
        self._visible = visible

    def set_reachable(self, reachable: bool, now: float):
        """
        Whether the plate can be reached. When it is back, its screen is taken soon, without waiting for the backoff: it
        may have restarted.
        """
        if reachable and not self._reachable:
            self._failures = 0
            self._error = None
            if self._finished_at is not None:
                self.screen_changed(ScreenChange.RECONNECTED, now)
        self._reachable = reachable

    def screen_changed(self, change: ScreenChange, now: float):
        """The screen of the plate changed: take a screenshot once changes have been quiet for `change.delay`."""
        if self._first_change is None:
            self._first_change = now
        due = now + change.delay
        if self._change_due is not None:
            due = max(due, self._change_due)
        self._change_due = min(due, self._first_change + MAX_CHANGE_WAIT)

    def refresh(self):
        """The user asks for a screenshot: right away (after the one that runs)."""
        self._manual = True

    def started(self):
        """A screenshot is taken now (`poll` said so). What was asked for until now is in it."""
        self._running = True
        self._manual = False
        self._change_due = None
        self._first_change = None

    def succeeded(self, now: float):
        self._running = False
        self._finished_at = self._updated_at = now
        self._failures = 0
        self._error = None

    def failed(self, error: str, now: float):
        self._running = False
        self._finished_at = now
        self._failures += 1
        self._error = error

    # --- when ---

    def poll(self, now: float) -> bool:
        """
        :return: whether to take a screenshot now; if so, it counts as started (see `started`)
        """
        due = self.next_wakeup()
        if due is None or due > now:
            return False
        self.started()
        return True

    def next_wakeup(self) -> Optional[float]:
        """:return: when the next screenshot is due (may be in the past), None while none is (or one runs, or paused)"""
        if self._running or self.paused is not None:
            return None
        if self._manual:
            # also during a backoff, and before the first one
            return float("-inf")
        candidates = []
        if self._finished_at is None:
            # the first image, as soon as the plate is shown
            candidates.append(float("-inf"))
        elif self._interval > 0:
            candidates.append(self._finished_at + self._interval)
        if self._change_due is not None:
            candidates.append(self._change_due)
        if not candidates:
            return None
        due = min(candidates)
        if self._failures:
            due = max(due, self._finished_at + backoff_delay(self._failures))
        return due

    @property
    def paused(self) -> Optional[str]:
        """:return: why no screenshot is taken now: "hidden" (the view doesn't show the plate), "unreachable", None"""
        if not self._visible:
            return "hidden"
        if not self._reachable:
            return "unreachable"
        return None

    @property
    def running(self) -> bool:
        return self._running

    def state(self) -> ScreenshotState:
        due = self.next_wakeup()
        return ScreenshotState(
            running=self._running,
            paused=self.paused,
            error=self._error,
            failures=self._failures,
            next_at=None if due is None or due == float("-inf") else due,
            updated_at=self._updated_at,
        )


def age_text(updated_at: Optional[float], now: float) -> str:
    """:return: how long ago the image was taken, e.g. "updated 12 s ago" ("no image yet" before the first)"""
    if updated_at is None:
        return "no image yet"
    seconds = max(0, int(now - updated_at))
    if seconds < 5:
        return "updated just now"
    if seconds < 60:
        return f"updated {seconds} s ago"
    if seconds < 3600:
        return f"updated {seconds // 60} min ago"
    return f"updated {seconds // 3600} h ago"


def status_text(state: ScreenshotState, now: float) -> str:
    """:return: what the view says about the screenshots of the plate, next to the image"""
    if state.running:
        return "Taking a screenshot…"
    parts = []
    if state.error is not None:
        parts.append(f"Screenshot failed: {state.error}")
    else:
        parts.append(age_text(state.updated_at, now).capitalize())
    if state.paused == "unreachable":
        parts.append("paused: the plate is offline or not connected yet")
    elif state.error is not None and state.next_at is not None:
        parts.append(f"retrying in {max(0, int(state.next_at - now))} s")
    return "  ·  ".join(parts)
