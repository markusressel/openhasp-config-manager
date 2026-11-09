"""
The tool windows of the main window, like those of IntelliJ: the views (docks) around the preview, with a strip of buttons
(a rail) at the left, right and bottom edge of the window. Qt-free: the widgets are in `gui/qt/window/tool_window_rails.py`.

Each rail has two groups of buttons, at its start and at its end. Each group is a place next to the preview (a `Slot`): the
left and the right side have a top and a bottom place, the bottom has a left and a right one. A place shows one view at a
time (opening another view of its group closes the one that was open), the places show their views at the same time: the
two of a side split it. A view moves to another place by dragging its button to another group, or with its context menu.

`ToolWindowLayout` is the arrangement: the views of each place in the order of their buttons, which views are open, and the
size of each place. The window builds its docks from it, so it is the only arrangement there is.
"""

import math
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Dict, List, Optional, Sequence, Set, Tuple


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTTOM = "bottom"

    @property
    def vertical(self) -> bool:
        """The rail of the side runs from top to bottom."""
        return self in (Side.LEFT, Side.RIGHT)


class Slot(StrEnum):
    """A place for views next to the preview: one of the two groups of buttons of a rail."""

    LEFT_TOP = "left_top"
    LEFT_BOTTOM = "left_bottom"
    RIGHT_TOP = "right_top"
    RIGHT_BOTTOM = "right_bottom"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"

    @property
    def side(self) -> Side:
        return Side(self.value.split("_")[0])

    @property
    def secondary(self) -> bool:
        """The group at the end of its rail: below on the left and right, at the right at the bottom."""
        return self in (Slot.LEFT_BOTTOM, Slot.RIGHT_BOTTOM, Slot.BOTTOM_RIGHT)

    @property
    def label(self) -> str:
        """For a menu: "Left top"."""
        return self.value.replace("_", " ").capitalize()

    @staticmethod
    def of(side: Side, secondary: bool) -> "Slot":
        return next(slot for slot in Slot if slot.side == side and slot.secondary == secondary)

    def partner(self) -> "Slot":
        """The other place of the same side, which splits the side with this one."""
        return Slot.of(self.side, not self.secondary)


class RailClick(Enum):
    """What a click on the button of a view does, like in IntelliJ."""

    SHOW = "show"
    HIDE = "hide"


def click_action(is_open: bool) -> RailClick:
    """:param is_open: the view is open (closing the one of its group that was open, see `ToolWindowLayout.others_open`)"""
    return RailClick.HIDE if is_open else RailClick.SHOW


def drop_target(side: Side, length: int, position: int, primary: Sequence[int], secondary: Sequence[int]) -> Tuple[Slot, int]:
    """
    Where a button dropped on a rail goes: the first half of the rail is the group at its start, the second half that at its
    end (also while a group has no buttons).

    :param length: the length of the rail
    :param position: where along the rail the button is dropped
    :param primary: the middle of each button of the group at the start, along the rail
    :param secondary: the same for the group at the end
    :return: the place, and the index among its buttons
    """
    at_end = position > length / 2
    centers = secondary if at_end else primary
    return Slot.of(side, at_end), sum(1 for center in centers if center < position)


@dataclass
class ToolWindowLayout:
    """
    The arrangement of the views, by their names (see the module). A view is known once it is added (`add`); what was
    remembered (`load`) for views that are not added yet waits for them.
    """

    # the views of each place, in the order of their buttons
    slots: Dict[Slot, List[str]] = field(default_factory=lambda: {slot: [] for slot in Slot})
    # the open views
    open: Set[str] = field(default_factory=set)
    # the size of each place as (width, height): of its views, the ones of a place share it
    sizes: Dict[Slot, Tuple[int, int]] = field(default_factory=dict)
    # where each view goes and whether it is open at first, in the order they were added
    _defaults: Dict[str, Tuple[Slot, bool]] = field(default_factory=dict)
    # what was remembered, by name: the place, the index in it, and whether the view was open
    _remembered: Dict[str, Tuple[Slot, int, bool]] = field(default_factory=dict)

    # --- views ---

    def add(self, name: str, slot: Slot, is_open: bool = False):
        """
        A view: in its remembered place and open if it was, else in `slot` (after its views) and open if `is_open`.
        """
        self._defaults[name] = (slot, is_open)
        remembered = self._remembered.get(name)
        if remembered is None:
            self.slots[slot].append(name)
            if is_open:
                self.open.add(name)
            return
        slot, _, was_open = remembered
        views = self.slots[slot]
        views.append(name)
        # in the remembered order, the views that weren't remembered after them
        order = list(self._defaults)
        views.sort(key=lambda view: (self._remembered.get(view, (None, math.inf))[1], order.index(view)))
        if was_open:
            self.open.add(name)

    def remove(self, name: str):
        for views in self.slots.values():
            if name in views:
                views.remove(name)
        self.open.discard(name)
        self._defaults.pop(name, None)

    @property
    def names(self) -> List[str]:
        return list(self._defaults)

    def slot_of(self, name: str) -> Slot:
        return next(slot for slot, views in self.slots.items() if name in views)

    def views(self, slot: Slot) -> List[str]:
        return list(self.slots[slot])

    def default_slot(self, name: str) -> Slot:
        return self._defaults[name][0]

    # --- open views ---

    def set_open(self, name: str, is_open: bool):
        if is_open:
            self.open.add(name)
        else:
            self.open.discard(name)

    def others_open(self, name: str) -> List[str]:
        """:return: the other open views of the place of a view: they close when it opens"""
        return [view for view in self.slots[self.slot_of(name)] if view != name and view in self.open]

    def shown(self, slot: Slot) -> Optional[str]:
        """:return: the open view of a place, None if none is open"""
        return next((view for view in self.slots[slot] if view in self.open), None)

    # --- arranging ---

    def move(self, name: str, slot: Slot, index: Optional[int] = None) -> bool:
        """
        Move a view to a place (also within its place), before the view at `index` there (at its end for None).
        An open view stays open: the open view of its new place closes.

        :return: whether it moved to another place
        """
        # the arrangement is the user's now: the remembered order would put views added later in a wrong place
        self._remembered = {}
        old = self.slot_of(name)
        views = self.slots[old]
        old_index = views.index(name)
        views.remove(name)
        target = self.slots[slot]
        # the index counts the view itself where it was
        if index is not None and old == slot and old_index < index:
            index -= 1
        if index is None or index > len(target):
            index = len(target)
        target.insert(max(index, 0), name)
        if name in self.open:
            for other in self.others_open(name):
                self.open.discard(other)
        return old != slot

    def reset(self):
        """Every view back to its first place, open if it was at first; the remembered arrangement is forgotten."""
        self._remembered = {}
        self.slots = {slot: [] for slot in Slot}
        self.open = set()
        self.sizes = {}
        for name, (slot, is_open) in self._defaults.items():
            self.slots[slot].append(name)
            if is_open:
                self.open.add(name)

    def normalize(self):
        """At most one open view per place: the first one of its buttons stays."""
        for slot in Slot:
            shown = self.shown(slot)
            for view in self.slots[slot]:
                if view != shown:
                    self.open.discard(view)

    # --- settings ---

    def to_json(self) -> Dict:
        return {
            "slots": {slot.value: list(views) for slot, views in self.slots.items() if views},
            "open": sorted(self.open),
            "sizes": {slot.value: list(size) for slot, size in self.sizes.items()},
        }

    def load(self, value) -> bool:
        """
        Remember an arrangement (of `to_json`), before the views are added.

        :return: False for a value that isn't one (an older or broken setting); nothing is remembered then
        """
        try:
            remembered = {}
            for slot, views in value["slots"].items():
                for index, name in enumerate(views):
                    remembered[str(name)] = (Slot(slot), index, False)
            for name in value["open"]:
                if name in remembered:
                    slot, index, _ = remembered[name]
                    remembered[name] = (slot, index, True)
            sizes = {Slot(slot): (int(size[0]), int(size[1])) for slot, size in value.get("sizes", {}).items()}
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            return False
        self._remembered = remembered
        self.sizes = sizes
        return True
