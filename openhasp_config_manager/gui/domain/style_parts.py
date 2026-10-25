"""
The two digits at the end of an openHASP style property (`bg_color20`, `radius00`, `line_width11`). Qt-free.

A style property applies to one *part* of an object in one *state*. The suffix is `<part><state>`: the tens digit is the part, the
units digit the state. A property without a suffix is the same as `00`: the main part in the default state.
See https://www.openhasp.com/0.7.0/design/styling/ and the page of each object in https://www.openhasp.com/0.7.0/design/objects/.
"""

from enum import IntEnum
from typing import Dict


class Part(IntEnum):
    """The part of an object a style applies to (tens digit). What a part is depends on the object, see `OBJECT_PARTS`."""

    MAIN = 0
    INDICATOR = 1  # also the needle of a gauge or line meter, highlighting the current value
    KNOB = 2  # can be used to change the value
    ITEMS_BACKGROUND = 3  # the background of the items/buttons
    ITEMS = 4  # the items/buttons
    SELECTED = 5  # the selected item
    TICKS = 6  # the major ticks of the gauge
    CURSOR = 7  # the text cursor
    SCROLLBAR = 8
    OTHER = 9  # another special part


class State(IntEnum):
    """The state of an object a style applies to (units digit)."""

    DEFAULT = 0
    TOGGLED = 1
    PRESSED = 2  # pressed, not toggled
    PRESSED_TOGGLED = 3
    DISABLED = 4  # disabled, not toggled
    DISABLED_TOGGLED = 5


PART_DESCRIPTIONS: Dict[Part, str] = {
    Part.MAIN: "the main part of the object (the background)",
    Part.INDICATOR: "the indicator or needle, highlighting the current value",
    Part.KNOB: "the knob which can be used to change the value",
    Part.ITEMS_BACKGROUND: "the background of the items/buttons",
    Part.ITEMS: "the items/buttons",
    Part.SELECTED: "the selected item",
    Part.TICKS: "the major ticks of the gauge",
    Part.CURSOR: "the text cursor",
    Part.SCROLLBAR: "the scrollbar",
    Part.OTHER: "another special part",
}

STATE_DESCRIPTIONS: Dict[State, str] = {
    State.DEFAULT: "default",
    State.TOGGLED: "toggled",
    State.PRESSED: "pressed, not toggled",
    State.PRESSED_TOGGLED: "pressed and toggled",
    State.DISABLED: "disabled, not toggled",
    State.DISABLED_TOGGLED: "disabled and toggled",
}

# what the parts are for the objects whose documentation says so, by their `obj`
OBJECT_PARTS: Dict[str, Dict[Part, str]] = {
    "switch": {Part.INDICATOR: "the indicator (the colored track)", Part.KNOB: "the knob"},
    "arc": {Part.INDICATOR: "the indicator arc", Part.KNOB: "the knob"},
    "spinner": {Part.MAIN: "the background circle", Part.INDICATOR: "the spinning segment"},
    "tabview": {Part.ITEMS: "the tab buttons"},
}


def style_key(name: str, part: Part = Part.MAIN, state: State = State.DEFAULT) -> str:
    """
    :param name: a style property without suffix, e.g. `bg_color`
    :return: the key of the property for a part and state, e.g. `bg_color20` for the knob (`Part.KNOB`)
    """
    return f"{name}{int(part)}{int(state)}"
