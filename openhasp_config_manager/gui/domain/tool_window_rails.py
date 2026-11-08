"""
The tool window rails of the main window, like those of IntelliJ: a strip of buttons at each edge of the window, one per
view (dock), on the side where the view is. Qt-free: the widgets are in `gui/qt/window/tool_window_rails.py`.

All docks of the window are nested in one dock area around the preview, so the area of a dock doesn't tell where it is:
the side of a view is where it is next to the preview (`place`). A hidden view has no place on the screen; it keeps the
one it had last (`Placement`, remembered across restarts).
"""

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Dict, Hashable, Iterable, List, Optional, Tuple


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"

    @property
    def vertical(self) -> bool:
        """The rail of the side runs from top to bottom."""
        return self in (Side.LEFT, Side.RIGHT)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class Placement:
    """
    Where the button of a view goes: its rail, and where along it (the views are ordered like on the screen). The views of
    a tab group have one position, and are ordered like their tabs.
    """

    side: Side
    position: int
    tab: int = 0

    def to_json(self) -> Dict:
        return {"side": self.side.value, "position": self.position, "tab": self.tab}

    @staticmethod
    def from_json(value) -> Optional["Placement"]:
        """:return: the placement, None for a value that isn't one (an older or broken setting)"""
        try:
            return Placement(Side(value["side"]), int(value["position"]), int(value.get("tab", 0)))
        except (KeyError, TypeError, ValueError):
            return None


def side_of(rect: Rect, center: Rect) -> Side:
    """
    :param rect: where a view is
    :param center: where the preview is
    :return: the side of the preview the view is on. A view next to the preview and also above or below it (in a column
             at the left that reaches below the preview) is at the left or right.
    """
    if rect.right <= center.x:
        return Side.LEFT
    if rect.x >= center.right:
        return Side.RIGHT
    if rect.y >= center.bottom:
        return Side.BOTTOM
    if rect.bottom <= center.y:
        return Side.TOP
    # overlapping (not in a layout of docks): the direction it is moved most
    dx = (rect.x + rect.width / 2) - (center.x + center.width / 2)
    dy = (rect.y + rect.height / 2) - (center.y + center.height / 2)
    if abs(dx) >= abs(dy):
        return Side.LEFT if dx < 0 else Side.RIGHT
    return Side.TOP if dy < 0 else Side.BOTTOM


def place(rect: Rect, center: Rect, tab: int = 0) -> Placement:
    """
    :param tab: the index of the view in its tab group
    :return: the placement of the button of a view at `rect`, next to the preview at `center`
    """
    side = side_of(rect, center)
    return Placement(side, rect.y if side.vertical else rect.x, tab)


class RailClick(Enum):
    """What a click on the button of a view does, like in IntelliJ."""

    SHOW = "show"
    RAISE = "raise"
    HIDE = "hide"


def click_action(is_open: bool, is_raised: bool) -> RailClick:
    """
    :param is_open: the view is open (not closed), maybe behind another view of its tab group
    :param is_raised: the view can be seen: open and the current one of its tab group
    """
    if not is_open:
        return RailClick.SHOW
    if not is_raised:
        return RailClick.RAISE
    return RailClick.HIDE


def arrange(placements: Iterable[Tuple[Hashable, Placement]]) -> Dict[Side, List[Hashable]]:
    """
    :param placements: the views with their placements, in the order they were added to the window
    :return: the views of each side, in the order along the rail; those of a tab group in the order of their tabs
    """
    rails: Dict[Side, List[Tuple[int, int, int, Hashable]]] = {side: [] for side in Side}
    for index, (key, placement) in enumerate(placements):
        rails[placement.side].append((placement.position, placement.tab, index, key))
    return {side: [entry[3] for entry in sorted(entries, key=lambda entry: entry[:3])] for side, entries in rails.items()}
