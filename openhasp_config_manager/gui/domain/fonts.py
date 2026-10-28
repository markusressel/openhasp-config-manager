"""The fonts of the plate, picked like the firmware of openHASP does (`haspPayloadToFont` and `get_font`). Qt-free."""

import enum
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from openhasp_config_manager.processing.references import font_file_name

# the sizes of the fonts built into the firmware (bitmap fonts made from Roboto Condensed)
BUILT_IN_FONT_SIZES = (12, 16, 24, 32)
# the font of an object that doesn't say (`LV_FONT_DEFAULT` of a 320 pixels high screen)
DEFAULT_FONT_SIZE = 24
# `text_font` 0 to 7 are the ids of fonts: 0 is the small font of the theme, 1 to 3 its default font, the others are not set
_FONT_IDS = {0: 16, 1: DEFAULT_FONT_SIZE, 2: DEFAULT_FONT_SIZE, 3: DEFAULT_FONT_SIZE}
_LAST_FONT_ID = 7
# `text_font` 8 is the pixel font unscii, which is 8 pixels high
PIXEL_FONT_SIZE = 8


class FontKind(enum.Enum):
    # one of `BUILT_IN_FONT_SIZES`
    BUILT_IN = "built-in"
    # any other size, from the Roboto Condensed TrueType font in the firmware
    TRUETYPE = "truetype"
    # unscii, see `PIXEL_FONT_SIZE`
    PIXEL = "pixel"
    # a font file on the plate: `<name>.bin`, or `<name>.ttf` in the size at the end of the name
    FILE = "file"


@dataclass(frozen=True)
class PlateFont:
    size: int
    kind: FontKind
    # the name of the font file, for `FontKind.FILE`
    file: Optional[str] = None


DEFAULT_FONT = PlateFont(DEFAULT_FONT_SIZE, FontKind.BUILT_IN)


def resolve_font(value, font_files: Iterable[str] = (), default: PlateFont = DEFAULT_FONT) -> PlateFont:
    """
    :param value: the `text_font` of an object: the id or size of a built-in font, or the name of a font file
    :param font_files: the names of the font files on the plate (`arial.ttf`, `arial_20.bin`)
    :param default: the font of the object, which a value the plate can't load (or none, or a template that is not rendered)
        doesn't change
    :return: the font the plate shows the text in
    """
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    payload = str(value).strip()
    if payload.isdigit():
        number = int(payload)
        if number <= _LAST_FONT_ID:
            return _font_id(number, default)
        if number == PIXEL_FONT_SIZE:
            return PlateFont(PIXEL_FONT_SIZE, FontKind.PIXEL)
        if number in BUILT_IN_FONT_SIZES:
            return PlateFont(number, FontKind.BUILT_IN)
    return _font_file(payload, font_files) or _truetype(payload) or default


def font_size(value, font_files: Iterable[str] = (), default: int = DEFAULT_FONT_SIZE) -> int:
    """:return: the size of the font of a `text_font` (see `resolve_font`), the default if the plate wouldn't change the font"""
    return resolve_font(value, font_files, PlateFont(default, FontKind.BUILT_IN)).size


def _font_id(number: int, default: PlateFont) -> PlateFont:
    size = _FONT_IDS.get(number)
    return PlateFont(size, FontKind.BUILT_IN) if size else default


def _font_file(payload: str, font_files: Iterable[str]) -> Optional[PlateFont]:
    """:return: the font of the font file on the plate that the payload names, if there is one"""
    name = font_file_name(payload, font_files)
    if not name:
        return None
    size = re.search(r"(\d+)$", payload)
    return PlateFont(int(size[1]) if size else DEFAULT_FONT_SIZE, FontKind.FILE, name)


def _truetype(payload: str) -> Optional[PlateFont]:
    """:return: the TrueType font of the firmware, in the size the payload starts with (`atoi`), if that is more than 8"""
    digits = re.match(r"\d+", payload)
    size = int(digits[0]) if digits else 0
    return PlateFont(size, FontKind.TRUETYPE) if size > PIXEL_FONT_SIZE else None
