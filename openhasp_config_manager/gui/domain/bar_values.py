"""
The values of a bar or slider that LVGL v7.11 draws and a finger changes (`lv_bar.c`, `lv_slider.c`). Qt-free.

A slider has a `type`: 0 normal, 1 symmetrical (the indicator grows from 0 when the range goes below and above it), 2 range (a second knob
moves `start_value`, the indicator is between the knobs). A bar has no `type` in openHASP, but its `start_value` moves the start of the
indicator, like the left knob of a range slider.
"""

from typing import Optional

SLIDER_NORMAL, SLIDER_SYMMETRICAL, SLIDER_RANGE = 0, 1, 2


def _int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def bar_range(data: dict, slider: bool) -> tuple[int, int, int, int]:
    """
    :return: `min`, `max`, the start and `val` of a bar or slider, the values limited like LVGL limits them: `val` to the range,
        the start to the range and to at most `val`. `lv_bar_set_type` puts the start at `min` for any type but range, so a `type`
        after the `start_value` (the properties are set in the order of the file) resets it, one before it does not. A bar has no `type`.
    """
    minimum, maximum = _int(data.get("min"), 0), _int(data.get("max"), 100)
    value = min(max(_int(data.get("val"), 0), minimum), maximum)
    start = minimum
    for key in data:
        if key == "start_value":
            start = _int(data[key], minimum)
        elif slider and key == "type" and _int(data[key], SLIDER_NORMAL) % 3 != SLIDER_RANGE:
            start = minimum
    start = min(max(start, minimum), value)
    return minimum, maximum, start, value


def slider_type(data: dict) -> int:
    """`lv_slider_set_type(obj, val % 3)`"""
    return _int(data.get("type"), SLIDER_NORMAL) % 3


def indicator_span(data: dict, slider: bool) -> Optional[tuple[float, float]]:
    """
    :param slider: whether the object is a slider (it has a `type`), else a bar
    :return: where the indicator starts and ends, as fractions of the track (0 left or bottom, 1 right or top), None if LVGL draws none
    """
    minimum, maximum, start, value = bar_range(data, slider)
    span = maximum - minimum
    if span <= 0:
        return None
    begin, end = (start - minimum) / span, (value - minimum) / span
    if slider and slider_type(data) == SLIDER_SYMMETRICAL and minimum < 0 < maximum and start == minimum:
        zero = -minimum / span
        return (min(zero, end), max(zero, end))
    if end - begin <= 0:
        return None
    return begin, end


def pressed_knob(finger: float, left_knob: tuple[float, float], right_knob: tuple[float, float], vertical: bool) -> str:
    """
    `LV_SIGNAL_PRESSED` of a range slider: which knob the finger moves, "start" (the left knob, `start_value`) or "val" (the right one).
    :param finger: where the finger is along the slider (x, or y if vertical), in pixels
    :param left_knob, right_knob: where the knobs begin and end along the slider (top and bottom if vertical)
    """
    if vertical:
        # the start knob is the lower one, the value knob the upper one
        if finger < right_knob[0]:
            return "val"
        if finger > left_knob[1]:
            return "start"
    else:
        if finger > right_knob[1]:
            return "val"
        if finger < left_knob[0]:
            return "start"
    left_distance = abs((left_knob[0] + left_knob[1]) / 2 - finger)
    right_distance = abs((right_knob[0] + right_knob[1]) / 2 - finger)
    return "val" if right_distance < left_distance else "start"
