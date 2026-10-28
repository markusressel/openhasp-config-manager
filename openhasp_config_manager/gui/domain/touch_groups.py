"""
Objects with the same `groupid` follow each other: when one is toggled or changes its value, the others take the same value
(`event_update_group` and `attribute_set_normalized_value` in the firmware). Qt-free.
"""

from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from openhasp_config_manager.gui.domain.interaction import Key, is_true, object_key
from openhasp_config_manager.gui.domain.tabs import tab_texts

# the range of the toggles and of what a button reports: off and on
OFF, ON = 0, 1
_DEFAULT_RANGE = (0, 100)


def group_of(obj: Mapping) -> int:
    """:return: the `groupid` of an object, 0 if it has none (0 is no group)"""
    try:
        return int(obj.get("groupid") or 0)
    except (TypeError, ValueError):
        return 0


def value_range(obj: Mapping, objects: Iterable[Mapping] = ()) -> Optional[Tuple[int, int]]:
    """
    :param objects: the objects of the plate (a tabview counts its tabs in them)
    :return: the range of the `val` of an object that can follow a group (`my_obj_get_range`), None for the others
    """
    kind = obj.get("obj")
    if kind == "btn":
        return (OFF, ON) if is_true(obj.get("toggle"), False) else None
    if kind in ("checkbox", "switch"):
        return OFF, ON
    if kind == "led":
        return 0, 255
    if kind in ("slider", "arc", "bar", "gauge", "linemeter"):
        try:
            return int(obj.get("min", _DEFAULT_RANGE[0])), int(obj.get("max", _DEFAULT_RANGE[1]))
        except (TypeError, ValueError):
            return _DEFAULT_RANGE
    if kind in ("dropdown", "roller"):
        count = len(str(obj["options"]).split("\n")) if obj.get("options") else 0
        return (0, count - 1) if count > 1 else None
    if kind == "tabview":
        count = len(tab_texts(list(objects), dict(obj)))
        return (0, count - 1) if count > 1 else None
    return None


def _map(value: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
    """The `map` of the firmware: integer math, rounding towards zero like C does."""
    numerator = (value - in_min) * (out_max - out_min)
    denominator = in_max - in_min
    quotient = abs(numerator) // abs(denominator)
    return (quotient if (numerator < 0) == (denominator < 0) else -quotient) + out_min


def group_values(
    objects: List[Mapping], source: Mapping, power: bool, value: int, minimum: int, maximum: int
) -> Dict[Key, int]:
    """
    :param objects: all objects of the plate, on every page
    :param source: the object that changed, in a group (the others follow it, it doesn't)
    :param power: whether the source is on
    :param value, minimum, maximum: its value, in its range
    :return: the new `val` of the objects that follow, by object
    """
    group = group_of(source)
    if group == 0 or minimum == maximum:
        return {}
    result = {}
    for obj in objects:
        if obj is source or group_of(obj) != group:
            continue
        target_range = value_range(obj, objects)
        if target_range is None:
            continue
        # limit to the range, and a source that is off is at its minimum
        if not power or value <= minimum:
            normalized = minimum
        elif value >= maximum:
            normalized = maximum
        else:
            normalized = value
        if target_range == (OFF, ON):
            result[object_key(obj)] = 0 if normalized == minimum else 1
        else:
            result[object_key(obj)] = _map(normalized, minimum, maximum, *target_range)
    return result
