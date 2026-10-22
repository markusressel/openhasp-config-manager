from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class SnapResult:
    x: float
    y: float
    # the lines the rect was aligned to, to draw as guides
    guides_x: Tuple[float, ...] = field(default_factory=tuple)
    guides_y: Tuple[float, ...] = field(default_factory=tuple)


def snap_rect(
    rect: Rect,
    others: Sequence[Rect],
    bounds: Rect,
    grid: Optional[int],
    threshold: float,
) -> SnapResult:
    """
    Snaps a rect that is being dragged: to the edges and centers of other objects and of the plate (alignment guides)
    if one is within the threshold, otherwise to the grid.

    :param rect: the rect at the position it is dragged to
    :param others: the other objects on the page
    :param bounds: the plate
    :param grid: the grid size, or None to not snap to a grid
    :param threshold: the maximum distance to snap to an alignment line
    """
    targets = [*others, bounds]
    x, guides_x = _snap_axis(
        position=rect.x,
        size=rect.w,
        lines=[line for other in targets for line in (other.x, other.x + other.w / 2, other.x + other.w)],
        grid=grid,
        threshold=threshold,
    )
    y, guides_y = _snap_axis(
        position=rect.y,
        size=rect.h,
        lines=[line for other in targets for line in (other.y, other.y + other.h / 2, other.y + other.h)],
        grid=grid,
        threshold=threshold,
    )
    return SnapResult(x=x, y=y, guides_x=guides_x, guides_y=guides_y)


def _snap_axis(
    position: float,
    size: float,
    lines: Sequence[float],
    grid: Optional[int],
    threshold: float,
) -> Tuple[float, Tuple[float, ...]]:
    # start edge, center and end edge of the dragged rect
    offsets = (0, size / 2, size)

    best: Optional[Tuple[float, float]] = None  # (distance, snapped position)
    for line in lines:
        for offset in offsets:
            distance = abs(line - (position + offset))
            if distance <= threshold and (best is None or distance < best[0]):
                best = (distance, line - offset)

    if best is not None:
        snapped = best[1]
    elif grid:
        snapped = round(position / grid) * grid
    else:
        snapped = position

    guides = tuple(sorted({line for line in lines for offset in offsets if abs(line - (snapped + offset)) < 0.5}))
    return snapped, guides
