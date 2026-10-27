from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Dict, List, Tuple


class Severity(StrEnum):
    # something to know, not a problem (e.g. a variable that is not used)
    HINT = "hint"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Problem:
    severity: Severity
    # the (rendered) object of the draft the problem is about
    obj: Dict
    message: str


def object_name(obj: Dict) -> str:
    return f"p{obj.get('page')}b{obj.get('id')}"


# x, y, width and height of an object as drawn
Rect = Tuple[float, float, float, float]

# the size an object is drawn with if it has no w or h
DEFAULT_OBJECT_WIDTH = 80
DEFAULT_OBJECT_HEIGHT = 40


_GEOMETRY_DEFAULTS = {"x": 0, "y": 0, "w": DEFAULT_OBJECT_WIDTH, "h": DEFAULT_OBJECT_HEIGHT}


def geometry_value(obj: Dict, key: str) -> float:
    """
    :param key: x, y, w or h
    :return: the value as it is drawn: a number, or the default if the object has none or it is not a number (a template that
        can't be rendered, e.g. because the object it refers to is gone, see `find_problems`)
    """
    return number_or(obj.get(key), _GEOMETRY_DEFAULTS[key])


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number_or(value, default: float) -> float:
    """:return: the value if it is a number, otherwise the default (e.g. a template that can't be rendered stays a string)"""
    return value if _is_number(value) else default


def object_rect(obj: Dict) -> Rect:
    """:return: where an object is drawn"""
    return geometry_value(obj, "x"), geometry_value(obj, "y"), geometry_value(obj, "w"), geometry_value(obj, "h")


def find_problems(objects: List[Dict], screen_width: int, screen_height: int) -> List[Problem]:
    """
    :param objects: the rendered objects of one page
    :return: what is wrong with them, errors first
    """
    result = []
    ids = Counter(obj.get("id") for obj in objects)
    reported_ids = set()
    for obj in objects:
        if ids[obj.get("id")] > 1 and obj.get("id") not in reported_ids:
            # once per id, for its first object
            reported_ids.add(obj.get("id"))
            result.append(Problem(Severity.ERROR, obj, f"{object_name(obj)}: the id is used by {ids[obj.get('id')]} objects"))

        for key in _GEOMETRY_DEFAULTS:
            if key in obj and not _is_number(obj[key]):
                result.append(Problem(Severity.ERROR, obj, f"{object_name(obj)}: {key} is not a number: {obj[key]}"))

        sides = _sides_outside(object_rect(obj), screen_width, screen_height)
        if sides:
            result.append(Problem(Severity.WARNING, obj, f"{object_name(obj)} is outside of the screen: {sides}"))
    return sorted(result, key=lambda problem: problem.severity != Severity.ERROR)


def _sides_outside(rect: Rect, screen_width: int, screen_height: int) -> str:
    """:return: e.g. "left by 4 px, bottom by 20 px", empty if the rect is on the screen"""
    x, y, w, h = rect
    sides = {"left": -x, "top": -y, "right": x + w - screen_width, "bottom": y + h - screen_height}
    return ", ".join(f"{side} by {round(amount)} px" for side, amount in sides.items() if amount > 0)
