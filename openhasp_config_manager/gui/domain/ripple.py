from dataclasses import dataclass
from typing import List

# how long a click ripple grows and fades, in seconds
RIPPLE_DURATION = 0.4
# the radius it grows to, in screen pixels
RIPPLE_RADIUS = 28


@dataclass(frozen=True)
class Ripple:
    """A circle that grows and fades where the user clicked in the preview, so it is clear that the page reacts."""

    x: float
    y: float
    started: float

    def progress(self, now: float) -> float:
        """:return: 0 when it started, 1 when it is over"""
        return min(1.0, max(0.0, (now - self.started) / RIPPLE_DURATION))

    def radius(self, now: float) -> float:
        # ease out: fast at first, then slowing down
        return RIPPLE_RADIUS * (1 - (1 - self.progress(now)) ** 3)

    def opacity(self, now: float) -> float:
        return 1.0 - self.progress(now)


def active_ripples(ripples: List[Ripple], now: float) -> List[Ripple]:
    return [ripple for ripple in ripples if ripple.progress(now) < 1.0]
