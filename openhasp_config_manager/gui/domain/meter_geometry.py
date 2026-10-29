"""Where the preview draws the values of arcs, gauges and line meters. Qt-free."""

from typing import List, Tuple

# (start, sweep) of an arc, in degrees clockwise from 3 o'clock
Span = Tuple[float, float]

_DEFAULT_LABEL_COUNT = 6


def number(value, default: float) -> float:
    """:return: the value of a property as a number, the default if it is none (e.g. a template that is not rendered)"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fraction(value, minimum, maximum) -> float:
    """:return: where a value is between the minimum and the maximum (0 to 1), 0 if the range is empty"""
    low, high = number(minimum, 0), number(maximum, 100)
    return 0.0 if high <= low else max(0.0, min((number(value, low) - low) / (high - low), 1.0))


def value_fraction(obj_data: dict) -> float:
    """:return: where the `val` of an object is between its `min` and `max` (0 to 1)"""
    return fraction(obj_data.get("val", 0), obj_data.get("min", 0), obj_data.get("max", 100))


def arc_angles(start_angle: float, end_angle: float, rotation: float, kind: int, value: float) -> Tuple[Span, Span]:
    """
    :param kind: the `type` of the arc: 0 fills from the start, 1 from the middle (symmetrical), 2 from the end (reverse)
    :param value: where the value is between `min` and `max` (0 to 1)
    :return: (start, sweep) of the background arc and (start, sweep) of the indicator
    """
    start = start_angle + rotation
    end = end_angle + rotation
    sweep = (end - start) % 360 or 360
    part = value * sweep
    if kind == 1:
        if part < sweep / 2:
            indicator = (start + part, sweep / 2 - part)
        else:
            indicator = (start + sweep / 2, part - sweep / 2)
    elif kind == 2:
        indicator = (start + part, sweep - part)
    else:
        indicator = (start, part)
    return (start, sweep), indicator


def gauge_labels(obj_data: dict) -> List[str]:
    """:return: the texts of the major ticks of a gauge, from the smallest to the largest value (`format` divides them by 10, ...)"""
    count = max(int(number(obj_data.get("label_count"), _DEFAULT_LABEL_COUNT)), 0)
    low, high = number(obj_data.get("min"), 0), number(obj_data.get("max"), 100)
    divider = 10 ** int(number(obj_data.get("format"), 0))
    return [str(int((low + (high - low) * index / max(count - 1, 1)) / divider)) for index in range(count)]


def active_lines(line_count: int, value: float) -> int:
    """:return: how many of the `line_count` lines of a line meter show a value (0 to 1)"""
    return round(value * line_count)
