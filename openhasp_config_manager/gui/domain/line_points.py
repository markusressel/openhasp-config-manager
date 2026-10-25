"""The `points` of a line object. Qt-free."""

import json
from typing import List, Tuple

Point = Tuple[float, float]


def parse_points(value) -> List[Point]:
    """
    :param value: the `points` property: a list of `[x, y]`, or the same as a JSON text
    :return: the points, leaving out everything that is not a pair of numbers (e.g. a template that is not rendered)
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    return [
        (float(point[0]), float(point[1]))
        for point in value
        if isinstance(point, (list, tuple))
        and len(point) == 2
        and all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in point)
    ]


def bounds(points: List[Point]) -> Tuple[float, float]:
    """:return: the width and height a line needs to show all its points (from 0,0)"""
    return (max((x for x, _ in points), default=0), max((y for _, y in points), default=0))
