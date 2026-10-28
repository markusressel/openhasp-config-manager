"""
The values a finger sets on sliders and arcs, computed like LVGL v7 does (`lv_slider_signal`, `lv_arc_signal`), integer math
included. Qt-free.
"""

from dataclasses import dataclass
from typing import Optional


def c_div(numerator: int, denominator: int) -> int:
    """Integer division like C does it: rounding towards zero."""
    quotient = abs(numerator) // abs(denominator)
    return quotient if (numerator < 0) == (denominator < 0) else -quotient


def lv_map(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
    """`_lv_map`: where `x` is between `in_min` and `in_max`, as a value between `out_min` and `out_max` (limited to them)."""
    if x >= in_max:
        return out_max
    if x <= in_min:
        return out_min
    return c_div((x - in_min) * (out_max - out_min), in_max - in_min) + out_min


def slider_value(position: int, length: int, pad_start: int, pad_end: int, minimum: int, maximum: int, vertical: bool) -> int:
    """
    The value of a slider (`LV_SIGNAL_PRESSING`) for a finger at `position`.

    :param position: where the finger is on the long side of the slider, in pixels from its left (from its top if vertical)
    :param length: the width of the slider (the height if vertical)
    :param pad_start, pad_end: the padding of the track at the left and right (top and bottom if vertical): the indicator is inside
    """
    inner = length - pad_start - pad_end
    if inner <= 0:
        return minimum
    span = maximum - minimum
    if vertical:
        # LVGL measures from the bottom edge plus the padding (not minus it, so a padded vertical slider is a bit off)
        value = c_div((length - 1 + pad_end - position) * span, inner) + minimum
    else:
        value = c_div((position - pad_start) * span, inner) + minimum
    return max(minimum, min(value, maximum))


def lvgl_atan2(x: int, y: int) -> int:
    """
    `_lv_atan2`: the angle in whole degrees (0..359) of a vector, clockwise from the y axis (so the arc calls it with y and x swapped to
    count from 3 o'clock), within one degree of the exact one. At least one of the two has to be non-zero.
    """
    flags_x, flags_y = x < 0, y < 0
    ux, uy = abs(x), abs(y)
    octant = ux > uy
    degree = (uy * 45) // ux if octant else (ux * 45) // uy
    if degree > 22:
        compensation = sum(degree <= limit for limit in (44, 41, 37, 32))
    else:
        compensation = sum(degree >= limit for limit in (2, 6, 10, 15))
    degree += compensation
    if octant:
        degree = 90 - degree
    if flags_y:
        degree = 180 + degree if flags_x else 180 - degree
    elif flags_x:
        degree = 360 - degree
    return degree


def arc_last_angle(kind: int, value: int, minimum: int, maximum: int, background_start: int, background_end: int) -> int:
    """
    :param kind: `type` of the arc: 0 normal, 1 symmetric, 2 reverse
    :return: the angle LVGL remembers for the value (`value_update`), where the indicator ends or starts
    """
    end = background_end + 360 if background_end < background_start else background_end
    if kind == 1:
        middle = (background_start + end) // 2
        value_middle = (minimum + maximum) // 2
        if value < value_middle:
            return lv_map(value, minimum, value_middle, background_start, middle)
        return lv_map(value, value_middle, maximum, middle, end)
    return lv_map(value, minimum, maximum, background_start, end)


# how fast the knob of an arc may turn, in degrees per second (`chg_rate` of LVGL)
ARC_CHANGE_RATE = 540


@dataclass
class ArcDrag:
    """What an adjustable arc remembers while a finger is on it (`dragging`, `min_close` and `last_tick` of its `ext`)."""

    dragging: bool = False
    # the last angle was nearer to the minimum than to the maximum, which decides where a jump over the gap goes
    min_close: bool = True
    last_tick: float = 0.0


def arc_value(
    drag: ArcDrag,
    dx: int,
    dy: int,
    radius: int,
    indicator_width: int,
    background_start: int,
    background_end: int,
    rotation: int,
    minimum: int,
    maximum: int,
    current_value: int,
    last_angle: int,
    now: float,
) -> Optional[int]:
    """
    The value of an adjustable arc for a finger at (dx, dy) from its center (`LV_SIGNAL_PRESSING`).

    LVGL turns the arc only once the finger is out on the ring (not in the inner third), never jumps over the gap between the end and the
    start of the scale, and limits how fast it turns (`ARC_CHANGE_RATE`).

    :param radius: the radius of the arc, without the padding of the background
    :param background_start, background_end: the angles of the background arc, clockwise from 3 o'clock (`start_angle`, `end_angle`)
    :param rotation: `rotation` of the arc
    :param current_value: the value of the arc now
    :param last_angle: the angle (in degrees, like `background_start`) the indicator ends at now
    :param now: the time in seconds, for the speed limit
    :return: the new value, None if the finger doesn't change it
    """
    if not drag.dragging:
        inner = radius - indicator_width
        inner -= inner // 2  # a more sensitive area
        if dx * dx + dy * dy > inner * inner:
            drag.dragging = True
            drag.last_tick = now
    if not drag.dragging or (dx == 0 and dy == 0):
        return None

    end = background_end + 360 if background_end < background_start else background_end
    angle = lvgl_atan2(dy, dx) - rotation - background_start
    if angle < 0:
        angle += 360
    degrees = end - background_start
    last_relative = last_angle - background_start
    # no big jumps: over the gap between the ends of the scale the angle goes to the end that was nearer
    if abs(angle - last_relative) > 180:
        angle = 0 if drag.min_close else degrees
    else:
        drag.min_close = angle < degrees // 2

    delta = angle - last_relative
    maximum_delta = int(ARC_CHANGE_RATE * round((now - drag.last_tick) * 1000) / 1000)
    delta = max(-maximum_delta, min(delta, maximum_delta))
    angle = last_relative + delta

    # rounding for symmetry
    rounding = c_div(degrees * 8, maximum - minimum)
    angle += (rounding + 4) >> 4
    angle += background_start

    value = lv_map(angle, background_start, end, minimum, maximum)
    # the time counts from the last change, and not while the finger rests on an end
    if value != current_value or value in (minimum, maximum):
        drag.last_tick = now
    return value
