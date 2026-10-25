"""What the preview items share: the colors of the default theme and how text is drawn."""

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


def plate_font(size) -> QtGui.QFont:
    """:return: the font for a `text_font` size of the plate"""
    pixel_size = int(float(size) * FONT_SCALE) if isinstance(size, (int, float)) else 17
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
