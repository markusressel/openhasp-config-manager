"""
Geometry of code-defined layouts: lengths, rectangles, padding, and the functions that split a length between children.
Everything here is pure; the layout containers (`Row`, `Column`, `Grid`) and the `Rect` helpers use the same functions, so
both declaration styles place objects identically.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

type Length = int | str
"""Pixels (`48`), or a percentage of the parent (`"25%"`)."""

_PERCENTAGE = re.compile(r"^\d+(\.\d+)?%$")


def resolve_length(length: Length, total: int) -> int:
    """
    A length in pixels: percentages are taken of `total`, rounded down, like `ObjectDimensionsProcessor` does for JSONL.
    """
    if isinstance(length, bool):
        raise TypeError(f"Invalid length: {length!r}")
    if isinstance(length, int):
        return length
    if isinstance(length, str) and _PERCENTAGE.match(length):
        return int(float(length[:-1]) * total / 100)
    raise ValueError(f"Invalid length: {length!r}, expected pixels (int) or a percentage like '25%'")


@dataclass(frozen=True)
class Weight:
    """A share of the space that is left after fixed sizes and gaps."""

    value: float = 1

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError(f"Weights must be positive: {self.value}")


type Size = Length | Weight
"""The size of a child along its parent's main axis."""


def split(length: int, sizes: Sequence[Size], gap: int = 0) -> List[Tuple[int, int]]:
    """
    Splits `length` between children, in order, with `gap` pixels between neighbours.

    Fixed sizes (pixels, or percentages of `length`) are taken first; the rest is shared by the weighted children. The
    shares are rounded so that they add up exactly: neighbouring children never have gaps or overlaps from rounding.

    :return: (offset, length) per child
    :raises ValueError: if the fixed sizes and gaps don't fit into `length`
    """
    if not sizes:
        return []
    fixed = [None if isinstance(size, Weight) else resolve_length(size, length) for size in sizes]
    weights = [size.value if isinstance(size, Weight) else 0 for size in sizes]
    remaining = length - sum(f for f in fixed if f is not None) - gap * (len(sizes) - 1)
    if remaining < 0:
        raise ValueError(
            f"Fixed sizes {list(sizes)} and gaps of {gap} need {length - remaining} pixels, only {length} available"
        )

    total_weight = sum(weights)
    result = []
    offset = 0
    cumulative_weight = 0.0
    shared = 0
    for size, weight in zip(fixed, weights):
        if size is None:
            cumulative_weight += weight
            # cumulative rounding: the shares always add up to exactly `remaining`
            end = int(remaining * cumulative_weight / total_weight)
            size = end - shared
            shared = end
        result.append((offset, size))
        offset += size + gap
    return result


@dataclass(frozen=True, init=False)
class Padding:
    """Space inside a container, around its children."""

    top: int
    right: int
    bottom: int
    left: int

    def __init__(
        self,
        all: int = 0,
        *,
        x: Optional[int] = None,
        y: Optional[int] = None,
        top: Optional[int] = None,
        right: Optional[int] = None,
        bottom: Optional[int] = None,
        left: Optional[int] = None,
    ):
        """`Padding(8)`, `Padding(x=6)`, `Padding(bottom=48)`: specific sides win over `x`/`y`, which win over `all`."""
        horizontal = all if x is None else x
        vertical = all if y is None else y
        object.__setattr__(self, "top", vertical if top is None else top)
        object.__setattr__(self, "right", horizontal if right is None else right)
        object.__setattr__(self, "bottom", vertical if bottom is None else bottom)
        object.__setattr__(self, "left", horizontal if left is None else left)

    @classmethod
    def of(cls, value: "int | Padding | None") -> "Padding":
        if value is None:
            return cls()
        if isinstance(value, Padding):
            return value
        return cls(value)


@dataclass(frozen=True)
class Rect:
    """
    A rectangle, relative to its parent (the screen, or the object it is placed in). `x`/`w` percentages are taken of the
    parent's width, `y`/`h` of its height, like in JSONL.

    The helpers (`inset()`, `rows()`, `cols()`, `grid()`) need pixel values: call `resolve()` first for a Rect with
    percentages.
    """

    x: Length
    y: Length
    w: Length
    h: Length

    def resolve(self, width: int, height: int) -> "Rect":
        """This rectangle in pixels, in a parent of the given size."""
        return Rect(
            x=resolve_length(self.x, width),
            y=resolve_length(self.y, height),
            w=resolve_length(self.w, width),
            h=resolve_length(self.h, height),
        )

    @property
    def is_resolved(self) -> bool:
        return all(isinstance(v, int) and not isinstance(v, bool) for v in (self.x, self.y, self.w, self.h))

    def _pixels(self) -> Tuple[int, int, int, int]:
        if not self.is_resolved:
            raise ValueError(f"{self} has percentages: resolve() it against its parent first")
        return self.x, self.y, self.w, self.h

    def offset(self, dx: int, dy: int) -> "Rect":
        x, y, w, h = self._pixels()
        return Rect(x + dx, y + dy, w, h)

    def inset(self, all: "int | Padding" = 0, *, x: Optional[int] = None, y: Optional[int] = None) -> "Rect":
        """This rectangle without a margin of `all` (or a `Padding`) on every side, or `x`/`y` horizontally/vertically."""
        padding = all if isinstance(all, Padding) else Padding(all, x=x, y=y)
        px, py, pw, ph = self._pixels()
        w = pw - padding.left - padding.right
        h = ph - padding.top - padding.bottom
        if w < 0 or h < 0:
            raise ValueError(f"{padding} does not fit into {self}")
        return Rect(px + padding.left, py + padding.top, w, h)

    def rows(self, *weights: float, gap: int = 0) -> List["Rect"]:
        """Splits this rectangle into rows, top to bottom, with heights in proportion to `weights`."""
        x, y, w, h = self._pixels()
        return [Rect(x, y + offset, w, length) for offset, length in split(h, [Weight(v) for v in weights], gap)]

    def cols(self, *weights: float, gap: int = 0) -> List["Rect"]:
        """Splits this rectangle into columns, left to right, with widths in proportion to `weights`."""
        x, y, w, h = self._pixels()
        return [Rect(x + offset, y, length, h) for offset, length in split(w, [Weight(v) for v in weights], gap)]

    def grid(self, rows: int, cols: int, gap: int = 0) -> List[List["Rect"]]:
        """Splits this rectangle into equal cells: one list per row."""
        return [row.cols(*[1] * cols, gap=gap) for row in self.rows(*[1] * rows, gap=gap)]
