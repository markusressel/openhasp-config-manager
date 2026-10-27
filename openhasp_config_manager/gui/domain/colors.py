"""Colors as they are written in the files (`"#0D0F14"`), for the color picker of the text editor. Qt-free."""

import re
from dataclasses import dataclass
from typing import Optional

_COLOR = re.compile(r"#(?P<hex>[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


@dataclass(frozen=True)
class Argb:
    """A color with the way it is written: `#RGB`, `#RRGGBB` or `#AARRGGBB` (the alpha first, like Qt writes it)."""

    red: int
    green: int
    blue: int
    alpha: int = 255
    # whether the hex digits are written in upper case
    upper: bool = True
    # whether the text has an alpha (8 digits)
    has_alpha: bool = False

    def hex(self) -> str:
        """:return: `#RRGGBB`, or `#AARRGGBB` if the color has an alpha (written, or not opaque)"""
        digits = f"{self.red:02x}{self.green:02x}{self.blue:02x}"
        if self.has_alpha or self.alpha != 255:
            digits = f"{self.alpha:02x}" + digits
        digits = digits.upper() if self.upper else digits
        return "#" + digits


def parse_color(text: str) -> Optional[Argb]:
    """:return: the color of a text like `#0D0F14`, None if it is not a color"""
    match = _COLOR.fullmatch(text)
    if match is None:
        return None
    digits = match.group("hex")
    upper = not any(char in "abcdef" for char in digits)
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    has_alpha = len(digits) == 8
    alpha = int(digits[:2], 16) if has_alpha else 255
    red, green, blue = (int(digits[i : i + 2], 16) for i in range(len(digits) - 6, len(digits), 2))
    return Argb(red, green, blue, alpha, upper, has_alpha)
