"""The places the user jumped from in the text editor, for the "back" and "forward" buttons of the mouse. Qt-free."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Location:
    path: Path
    # both starting at 1
    line: int
    column: int


class NavigationHistory:
    """Like the browser history: a jump records where it came from, going back records where it came back from."""

    def __init__(self, limit: int = 100):
        self._limit = limit
        self._back: List[Location] = []
        self._forward: List[Location] = []

    def jumped(self, origin: Location):
        """The user jumped away from `origin` (not by going back or forward): what could be reached by "forward" is lost."""
        if not self._back or self._back[-1] != origin:
            self._back.append(origin)
            del self._back[: -self._limit]
        self._forward.clear()

    def back(self, current: Location, exists=lambda location: True) -> Optional[Location]:
        """:return: where to go, None if there is no place before (or none that `exists`)"""
        return self._step(self._back, self._forward, current, exists)

    def forward(self, current: Location, exists=lambda location: True) -> Optional[Location]:
        return self._step(self._forward, self._back, current, exists)

    @staticmethod
    def _step(source: List[Location], other: List[Location], current: Location, exists) -> Optional[Location]:
        while source:
            target = source.pop()
            if target != current and exists(target):
                other.append(current)
                return target
        return None
