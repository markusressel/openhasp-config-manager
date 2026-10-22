from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Dict, List, Tuple


class Severity(StrEnum):
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


def find_problems(objects: List[Dict], rects: Dict[int, Rect], screen_width: int, screen_height: int) -> List[Problem]:
    """
    :param objects: the rendered objects of one page
    :param rects: id(object) -> where it is drawn (objects have a default size if they have no w and h)
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

        sides = _sides_outside(rects[id(obj)], screen_width, screen_height) if id(obj) in rects else ""
        if sides:
            result.append(Problem(Severity.WARNING, obj, f"{object_name(obj)} is outside of the screen: {sides}"))
    return sorted(result, key=lambda problem: problem.severity != Severity.ERROR)


def _sides_outside(rect: Rect, screen_width: int, screen_height: int) -> str:
    """:return: e.g. "left by 4 px, bottom by 20 px", empty if the rect is on the screen"""
    x, y, w, h = rect
    sides = {"left": -x, "top": -y, "right": x + w - screen_width, "bottom": y + h - screen_height}
    return ", ".join(f"{side} by {round(amount)} px" for side, amount in sides.items() if amount > 0)
