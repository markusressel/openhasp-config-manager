"""What the preview items share: the colors of the default theme and how text is drawn."""

import math
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain import fonts
from openhasp_config_manager.gui.domain.fonts import BUILT_IN_FONT_SIZES, FontKind, resolve_font

DEFAULT_TEXT = "#FFFFFF"
# the font of the plate if an object doesn't say
DEFAULT_FONT_SIZE = fonts.DEFAULT_FONT_SIZE
# the fonts of the plate, which are part of the package (see the README there)
_FONTS = Path(__file__).parents[3] / "fonts"
_PLATE_FONT_FILE = _FONTS / "RobotoCondensed-Regular.ttf"
_PIXEL_FONT_FILE = _FONTS / "unscii-8-thin.ttf"
# their families are renamed, so that neither an installed font nor a font file of the device is taken for them
_PLATE_FAMILY = "openHASP Roboto Condensed"
_PIXEL_FAMILY = "openHASP unscii"
# measured: a line of unscii is 16 pixels high on the plate (the `line_height` of its font in the firmware), not 8 like in Qt, and
# its glyphs are 3 pixels below the top of the line
_PIXEL_LEAD = 8
_PIXEL_TOP = 3
# no text is larger than the screen of a plate: a typo like `"text_font": 2400` would make every repaint slow
_MAX_PIXEL_SIZE = 480
# the angle of the scale of a gauge or line meter if the object doesn't say
DEFAULT_SCALE_ANGLE = 240


def to_color(value, default: str) -> QtGui.QColor:
    """:return: the color of a property, the default if there is none or it is not a color (e.g. a template that is not rendered)"""
    color = QtGui.QColor(value) if isinstance(value, str) else QtGui.QColor()
    return color if color.isValid() else QtGui.QColor(default)


def opacity(value, default: float = 255) -> float:
    """:return: an opacity property (0 to 255) as 0 to 1"""
    return max(0.0, min(number(value, default) / 255, 1.0))


# the font files of the device that is shown: their name on the plate -> the file, see `set_font_files`
_font_files: Dict[str, Path] = {}
# the font files that Qt loaded, and when they were changed -> the family of their font
_families: Dict[Tuple[Path, int], str] = {}


def set_font_files(files: Mapping[str, Path]):
    """:param files: the font files of the device: their name on the plate (`arial.ttf`, `arial_20.bin`) -> the file"""
    _font_files.clear()
    _font_files.update(files)


def plate_font(value) -> QtGui.QFont:
    """:return: the font for a `text_font` of the plate, see `resolve_font`"""
    plate = resolve_font(value, _font_files)
    family = _family(_PLATE_FONT_FILE) or _PLATE_FAMILY
    if plate.kind is FontKind.PIXEL:
        family = _family(_PIXEL_FONT_FILE) or family
    elif plate.kind is FontKind.FILE and plate.file.endswith(".ttf"):
        # a `.bin` font is drawn in Roboto Condensed: Qt can't read the format of LVGL
        family = _family(_font_files[plate.file]) or family
    font = QtGui.QFont(family)
    font.setPixelSize(min(max(plate.size, 1), _MAX_PIXEL_SIZE))
    return font


def _family(file: Path) -> Optional[str]:
    """:return: the family of the font in a file, which is loaded into Qt the first time (and again after it changed), none if Qt
    can't read it"""
    try:
        key = (file, file.stat().st_mtime_ns)
    except OSError:
        return None
    if key not in _families:
        font_id = QtGui.QFontDatabase.addApplicationFont(str(file))
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if not families:
            return None
        _families[key] = families[0]
    return _families[key]


def draw_text(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    text: str,
    color: QtGui.QColor,
    font: QtGui.QFont,
    align="center",
    valign="center",
):
    """Draw one line of text in a rect, centered vertically (`valign` "top": like the first line of a label). `align` is the `align`
    property of the object."""
    flags = {"left": QtCore.Qt.AlignmentFlag.AlignLeft, "right": QtCore.Qt.AlignmentFlag.AlignRight}.get(
        align, QtCore.Qt.AlignmentFlag.AlignHCenter
    )
    painter.setFont(font)
    painter.setPen(color)
    if valign == "top":
        painter.drawText(rect.translated(0, line_top(font)), int(flags | QtCore.Qt.AlignmentFlag.AlignTop), text)
    else:
        painter.drawText(
            rect.translated(0, line_top(font) - line_lead(font) / 2), int(flags | QtCore.Qt.AlignmentFlag.AlignVCenter), text
        )


def mix(first: QtGui.QColor, second: QtGui.QColor, amount: float) -> QtGui.QColor:
    """:return: the color between two colors, `amount` (0 to 1) of the way to the second"""
    return QtGui.QColor(*(round(a + (b - a) * amount) for a, b in zip(first.getRgb()[:3], second.getRgb()[:3])))


def wrap_lines(font: QtGui.QFont, text: str, width: float) -> list:
    """:return: the lines of a text that is wrapped at words to fit a width (a line break in the text starts a new line)"""
    metrics = QtGui.QFontMetricsF(font)
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and metrics.horizontalAdvance(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


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


def value_fraction(obj_data: dict) -> float:
    """:return: where the `val` of an object is between its `min` and `max` (0 to 1)"""
    return fraction(obj_data.get("val", 0), obj_data.get("min", 0), obj_data.get("max", 100))


def selected_index(obj_data: dict) -> int:
    """:return: the selected entry (`val`) of a dropdown or roller"""
    return int(number(obj_data.get("val"), 0))


def option_lines(options) -> list:
    """:return: the entries of an `options` property (separated by a line break, written `\\n` in the file)"""
    return str(options).split("\n") if options else []


def centered_square(width: float, height: float) -> QtCore.QRectF:
    """:return: the largest square in the middle of a width and height, like the circle objects (arc, spinner) are drawn in"""
    side = min(width, height)
    return QtCore.QRectF((width - side) / 2, (height - side) / 2, side, side)


def round_pen(color, width: float) -> QtGui.QPen:
    """:return: a pen with round caps and joins, like the strokes of the plate (arcs, needles, check marks)"""
    pen = QtGui.QPen(color, width)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    return pen


def polar(center: QtCore.QPointF, radius: float, degrees: float) -> QtCore.QPointF:
    """:return: the point at a distance from the center, in degrees clockwise from 3 o'clock (like the angles of openHASP)"""
    angle = math.radians(degrees)
    return QtCore.QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius)


def scale_start(angle: float, rotation: float) -> float:
    """:return: where a scale of `angle` degrees starts (clockwise from 3 o'clock): centered at the top, plus the rotation"""
    return 90 + (360 - angle) / 2 + rotation


def line_lead(font: QtGui.QFont) -> int:
    """:return: how much higher a line of the plate is than one of Qt, for the font (measured, the extra pixels are above the glyphs).
    Only the fonts built into the firmware have them: the plate renders the other sizes from a TrueType font, with the line height
    of Qt."""
    if font.family() == _PIXEL_FAMILY:
        return _PIXEL_LEAD
    if font.family() != _PLATE_FAMILY or font.pixelSize() not in BUILT_IN_FONT_SIZES:
        return 0
    return 4 if font.pixelSize() >= 32 else 3


def line_top(font: QtGui.QFont) -> int:
    """:return: how much of `line_lead` is above the glyphs of the first line"""
    if font.family() == _PIXEL_FAMILY:
        return _PIXEL_TOP
    lead = line_lead(font)
    # the built-in font of size 24 has one of its extra pixels below the glyphs
    return lead - (1 if lead and font.pixelSize() == 24 else 0)


def set_line_space(text_item, space: float):
    """Put `space` more pixels between the lines of the text of a `QGraphicsTextItem` (`text_line_space`)."""
    cursor = QtGui.QTextCursor(text_item.document())
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    block_format = QtGui.QTextBlockFormat()
    block_format.setLineHeight(space, QtGui.QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value)
    cursor.mergeBlockFormat(block_format)
