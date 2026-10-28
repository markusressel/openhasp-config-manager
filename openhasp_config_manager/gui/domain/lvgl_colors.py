"""
The color math of LVGL (v7, 16 bit display) and the colors the openHASP theme derives from its two theme colors. Qt-free.

The pressed looks of the preview can't be measured on a plate (the firmware has no touch injection): they are computed with the
formulas of `lv_theme_hasp.c` (`COLOR_BTN_PR` and friends) and written down as constants where they are used, with a test here that
the same formulas reproduce the colors that were measured (`#4ACAFF`, `#0081B4`, ...).
"""

from dataclasses import dataclass
from typing import Tuple

Rgb = Tuple[int, int, int]

# LV_OPA_x: the opacity LVGL names, 0..255
OPA_10, OPA_20, OPA_30, OPA_50, OPA_60 = 25, 51, 76, 127, 153

_WHITE: Rgb = (255, 255, 255)
_BLACK: Rgb = (0, 0, 0)
# the bits of a color channel on a 16 bit display (RGB565)
_BITS = (5, 6, 5)


def parse_hex(color: str) -> Rgb:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def to_hex(color: Rgb) -> str:
    return "#%02X%02X%02X" % color


def to_display(color: Tuple[float, float, float]) -> Rgb:
    """
    :return: the color the way a 16 bit display shows it: every channel is rounded to the steps of RGB565 and filled up again with
        its own high bits (what the screenshots of the plate show). Every `lv_color_t` of LVGL is one of these.
    """
    result = []
    for value, bits in zip(color, _BITS):
        steps = (1 << bits) - 1
        level = round(value * steps / 255)
        shift = 8 - bits
        result.append((level << shift) | (level >> (bits - shift)))
    return result[0], result[1], result[2]


def mix(first: Rgb, second: Rgb, amount: int) -> Rgb:
    """:return: `lv_color_mix`: `amount` (0..255) of the first color and the rest of the second"""
    return to_display(tuple((a * amount + b * (255 - amount)) / 255 for a, b in zip(first, second)))


def lighten(color: Rgb, amount: int) -> Rgb:
    """:return: `lv_color_lighten`: the color mixed with white"""
    return mix(_WHITE, color, amount)


def darken(color: Rgb, amount: int) -> Rgb:
    """:return: `lv_color_darken`: the color mixed with black"""
    return mix(_BLACK, color, amount)


@dataclass(frozen=True)
class ButtonColors:
    """The colors of a button of the theme (`styles->btn` in `lv_theme_hasp.c`), as `(background, gradient end)`."""

    normal: Tuple[Rgb, Rgb]
    pressed: Tuple[Rgb, Rgb]
    checked: Tuple[Rgb, Rgb]
    checked_pressed: Tuple[Rgb, Rgb]


def button_colors(primary: str, secondary: str) -> ButtonColors:
    """
    :param primary: `color1` of the plate (`HUE_COLOR` of the theme)
    :param secondary: `color2` of the plate (`CHK_COLOR`)
    """
    hue, check = to_display(parse_hex(primary)), to_display(parse_hex(secondary))
    # COLOR_BTN_CHK is the secondary color itself (`lv_color_lighten(CHK_COLOR, LV_OPA_0)`)
    checked = check
    checked_grad = darken(check, OPA_60)
    return ButtonColors(
        normal=(lighten(hue, OPA_30), darken(hue, OPA_30)),
        pressed=(lighten(hue, OPA_10), darken(hue, OPA_50)),
        checked=(checked, checked_grad),
        checked_pressed=(darken(checked, OPA_20), darken(checked_grad, OPA_20)),
    )
