"""What the preview items share: the colors of the default theme and how text is drawn."""

import math
import re

from PyQt6 import QtCore, QtGui

DEFAULT_ACCENT = "#558B2F"
DEFAULT_TRACK = "#313131"
DEFAULT_KNOB = "lightgray"
DEFAULT_TEXT = "#FFFFFF"
# the preview draws the fonts of the plate (pixel sizes) smaller, as it did for the first items
FONT_SCALE = 0.7


def to_color(value, default: str) -> QtGui.QColor:
    """:return: the color of a property, the default if there is none or it is not a color (e.g. a template that is not rendered)"""
    color = QtGui.QColor(value) if isinstance(value, str) else QtGui.QColor()
    return color if color.isValid() else QtGui.QColor(default)


def font_size(value, default: int = 25) -> float:
    """
    :param value: the `text_font` of an object: the size of a built-in font, or the name of a font file, which ends with its size
        (`arial20`, `arial_20`)
    :return: the size, the default if there is none (e.g. a template that is not rendered)
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    match = re.search(r"(\d+)$", value) if isinstance(value, str) else None
    return int(match[1]) if match else default


def plate_font(size) -> QtGui.QFont:
    """:return: the font for a `text_font` of the plate, see `font_size`"""
    pixel_size = int(float(font_size(size, 17)) * FONT_SCALE)
    return QtGui.QFont("Roboto Condensed", max(pixel_size, 1))


def draw_text(painter: QtGui.QPainter, rect: QtCore.QRectF, text: str, color: QtGui.QColor, font: QtGui.QFont, align="center"):
    """Draw one line of text in a rect, centered vertically. `align` is the `align` property of the object."""
    flags = {"left": QtCore.Qt.AlignmentFlag.AlignLeft, "right": QtCore.Qt.AlignmentFlag.AlignRight}.get(
        align, QtCore.Qt.AlignmentFlag.AlignHCenter
    )
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(rect, int(flags | QtCore.Qt.AlignmentFlag.AlignVCenter), text)


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


def option_lines(options) -> list:
    """:return: the entries of an `options` property (separated by a line break, written `\\n` in the file)"""
    return str(options).split("\n") if options else []


def polar(center: QtCore.QPointF, radius: float, degrees: float) -> QtCore.QPointF:
    """:return: the point at a distance from the center, in degrees clockwise from 3 o'clock (like the angles of openHASP)"""
    angle = math.radians(degrees)
    return QtCore.QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius)


def scale_start(angle: float, rotation: float) -> float:
    """:return: where a scale of `angle` degrees starts (clockwise from 3 o'clock): centered at the top, plus the rotation"""
    return 90 + (360 - angle) / 2 + rotation
