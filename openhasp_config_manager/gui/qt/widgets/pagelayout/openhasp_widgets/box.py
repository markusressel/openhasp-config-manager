"""The box every openHASP object part is drawn as: background (with gradient), border, outline and shadow, in the state of the object."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part, State
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget, state_fallback

# the properties of a box, with their value if neither the object nor the defaults of its type set them
_PROPERTIES: Dict[str, Any] = {
    "bg_color": "#FFFFFF",
    "bg_grad_color": "#FFFFFF",
    "bg_grad_dir": 0,
    "bg_main_stop": 0,
    "bg_grad_stop": 255,
    "bg_opa": 0,
    "radius": 0,
    "border_width": 0,
    "border_color": "#000000",
    "border_opa": 255,
    "border_side": 15,
    "outline_width": 0,
    "outline_color": "#000000",
    "outline_opa": 255,
    "outline_pad": 0,
    "shadow_width": 0,
    "shadow_color": "#000000",
    "shadow_opa": 255,
    "shadow_ofs_x": 0,
    "shadow_ofs_y": 0,
    "shadow_spread": 0,
}

# `border_side`: the sides that have a border, added together
BORDER_BOTTOM, BORDER_TOP, BORDER_LEFT, BORDER_RIGHT = 1, 2, 4, 8
BORDER_ALL = 15

GRADIENT_VERTICAL = 1
GRADIENT_HORIZONTAL = 2


@dataclass(frozen=True)
class BoxStyle:
    bg_color: QtGui.QColor
    bg_grad_color: QtGui.QColor
    bg_grad_dir: int
    bg_main_stop: int
    bg_grad_stop: int
    bg_opa: float
    radius: float
    border_width: float
    border_color: QtGui.QColor
    border_opa: float
    border_side: int
    outline_width: float
    outline_color: QtGui.QColor
    outline_opa: float
    outline_pad: float
    shadow_width: float
    shadow_color: QtGui.QColor
    shadow_opa: float
    shadow_ofs_x: float
    shadow_ofs_y: float
    shadow_spread: float


def default_value(defaults: Dict[str, Any], name: str, state: State, fallback: Any = None) -> Any:
    """
    :param defaults: what a type of object looks like without style properties: `name` for every state, `name@<state number>` for one
    :return: the default of a property in a state, with the same fallback to other states as the plate
    """
    for candidate in state_fallback(state):
        if f"{name}@{int(candidate)}" in defaults:
            return defaults[f"{name}@{int(candidate)}"]
    return defaults.get(name, _PROPERTIES.get(name, fallback))


def resolve(
    item: EditableWidget, name: str, part: Part, defaults: Dict[str, Any], state: Optional[State] = None, fallback: Any = None
) -> Any:
    """
    :return: the value of a style property of a part in a state. Like on the plate (LVGL), the most specific state wins: what the
        default theme says for a toggled button beats the `bg_color` of the object (which is for the default state), but not its
        `bg_color01`. In the same state, the object wins over the default theme.
    """
    state = item.state if state is None else state
    for candidate in state_fallback(state):
        found = item.own_style(name, part, candidate)
        if found is not None:
            return found
        key = name if candidate == State.DEFAULT else f"{name}@{int(candidate)}"
        if key in defaults:
            return defaults[key]
    return _PROPERTIES.get(name, fallback)


def box_style(
    item: EditableWidget, part: Part = Part.MAIN, defaults: Optional[Dict[str, Any]] = None, state: Optional[State] = None
) -> BoxStyle:
    """:return: the box of a part of an object, from its style properties, then the defaults of its type"""
    defaults = defaults or {}
    state = item.state if state is None else state

    def value(name: str):
        return resolve(item, name, part, defaults, state)

    def opacity(name: str) -> float:
        return max(0.0, min(number(value(name), 255) / 255, 1.0))

    return BoxStyle(
        bg_color=to_color(value("bg_color"), "#FFFFFF"),
        bg_grad_color=to_color(value("bg_grad_color"), "#FFFFFF"),
        bg_grad_dir=int(number(value("bg_grad_dir"), 0)),
        bg_main_stop=int(number(value("bg_main_stop"), 0)),
        bg_grad_stop=int(number(value("bg_grad_stop"), 255)),
        bg_opa=opacity("bg_opa"),
        radius=max(number(value("radius"), 0), 0),
        border_width=max(number(value("border_width"), 0), 0),
        border_color=to_color(value("border_color"), "#000000"),
        border_opa=opacity("border_opa"),
        border_side=int(number(value("border_side"), BORDER_ALL)),
        outline_width=max(number(value("outline_width"), 0), 0),
        outline_color=to_color(value("outline_color"), "#000000"),
        outline_opa=opacity("outline_opa"),
        outline_pad=number(value("outline_pad"), 0),
        shadow_width=max(number(value("shadow_width"), 0), 0),
        shadow_color=to_color(value("shadow_color"), "#000000"),
        shadow_opa=opacity("shadow_opa"),
        shadow_ofs_x=number(value("shadow_ofs_x"), 0),
        shadow_ofs_y=number(value("shadow_ofs_y"), 0),
        shadow_spread=number(value("shadow_spread"), 0),
    )


def padding(item: EditableWidget, part: Part, default: float = 0) -> Tuple[float, float, float, float]:
    """:return: the left, top, right and bottom padding (`pad_left`, ...) of a part"""
    return tuple(number(item.style(f"pad_{side}", default, part), default) for side in ("left", "top", "right", "bottom"))


def capped_radius(rect: QtCore.QRectF, radius: float) -> float:
    """Like LVGL, a radius is never more than half of the shorter side (Qt would stretch the corners to ellipses)."""
    return max(min(radius, rect.width() / 2, rect.height() / 2), 0.0)


def draw_rounded(painter: QtGui.QPainter, rect: QtCore.QRectF, radius: float):
    radius = capped_radius(rect, radius)
    painter.drawRoundedRect(rect, radius, radius)


def _with_opacity(color: QtGui.QColor, opacity: float) -> QtGui.QColor:
    color = QtGui.QColor(color)
    color.setAlphaF(color.alphaF() * opacity)
    return color


def _background_brush(style: BoxStyle, rect: QtCore.QRectF) -> QtGui.QBrush:
    first, last = _with_opacity(style.bg_color, style.bg_opa), _with_opacity(style.bg_grad_color, style.bg_opa)
    if style.bg_grad_dir not in (GRADIENT_VERTICAL, GRADIENT_HORIZONTAL):
        return QtGui.QBrush(first)
    if style.bg_grad_dir == GRADIENT_VERTICAL:
        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
    else:
        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
    start, stop = style.bg_main_stop / 255, style.bg_grad_stop / 255
    gradient.setColorAt(0, first)
    gradient.setColorAt(min(start, 1.0), first)
    gradient.setColorAt(min(max(stop, start), 1.0), last)
    gradient.setColorAt(1, last)
    return QtGui.QBrush(gradient)


def _draw_shadow(painter: QtGui.QPainter, rect: QtCore.QRectF, style: BoxStyle):
    """
    The shadow: the box moved by the offset and grown by the spread, faded out over `shadow_width` pixels around its edge (measured on a
    plate: full at half the width inside of the edge, nothing at half the width outside, smoothly in between).
    """
    blur = style.shadow_width
    base = rect.translated(style.shadow_ofs_x, style.shadow_ofs_y).adjusted(
        *([-style.shadow_spread] * 2), *([style.shadow_spread] * 2)
    )
    steps = max(round(blur), 1)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    covered = 0.0
    for step in range(steps + 1):
        # from the outside to the inside of the faded edge
        distance = blur / 2 - blur * step / steps
        t = (blur / 2 - distance) / blur
        target = style.shadow_opa * t * t * (3 - 2 * t)
        if target <= covered:
            continue
        painter.setBrush(_with_opacity(style.shadow_color, (target - covered) / (1 - covered)))
        ring = base.adjusted(-distance, -distance, distance, distance)
        if ring.width() > 0 and ring.height() > 0:
            draw_rounded(painter, ring, style.radius + distance)
        covered = target


def _draw_border_sides(painter: QtGui.QPainter, rect: QtCore.QRectF, style: BoxStyle):
    """The border on some sides only: strips along these sides, inside of the rounded box."""
    width = style.border_width
    strips = {
        BORDER_BOTTOM: QtCore.QRectF(rect.left(), rect.bottom() - width, rect.width(), width),
        BORDER_TOP: QtCore.QRectF(rect.left(), rect.top(), rect.width(), width),
        BORDER_LEFT: QtCore.QRectF(rect.left(), rect.top(), width, rect.height()),
        BORDER_RIGHT: QtCore.QRectF(rect.right() - width, rect.top(), width, rect.height()),
    }
    inside = QtGui.QPainterPath()
    inside.addRoundedRect(rect, capped_radius(rect, style.radius), capped_radius(rect, style.radius))
    painter.setClipPath(inside)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(_with_opacity(style.border_color, style.border_opa))
    for side, strip in strips.items():
        if style.border_side & side:
            painter.drawRect(strip)
    painter.setClipping(False)


def draw_box(painter: QtGui.QPainter, rect: QtCore.QRectF, style: BoxStyle):
    """Draw the shadow, background, border and outline of a part, like LVGL: the border is inside of the rect, the outline outside."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    if style.shadow_width > 0 and style.shadow_opa > 0:
        _draw_shadow(painter, rect, style)

    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(_background_brush(style, rect))
    draw_rounded(painter, rect, style.radius)

    if style.border_width > 0 and style.border_opa > 0 and style.border_side & BORDER_ALL != BORDER_ALL:
        _draw_border_sides(painter, rect, style)
    elif style.border_width > 0 and style.border_opa > 0:
        pen = QtGui.QPen(_with_opacity(style.border_color, style.border_opa), style.border_width)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        half = style.border_width / 2
        draw_rounded(painter, rect.adjusted(half, half, -half, -half), style.radius - half)

    if style.outline_width > 0 and style.outline_opa > 0:
        pen = QtGui.QPen(_with_opacity(style.outline_color, style.outline_opa), style.outline_width)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        grow = style.outline_pad + style.outline_width / 2
        draw_rounded(painter, rect.adjusted(-grow, -grow, grow, grow), style.radius + grow)

    painter.restore()
