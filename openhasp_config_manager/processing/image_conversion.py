"""
Converts images to the binary format of openHASP's LVGL (the "Binary RGB565" output of the LVGL image converter), which the plate reads
from flash on each draw instead of decoding the PNG into memory (https://www.openhasp.com/0.7.0/design/objects/img/).

The file is a 4 byte header followed by the pixels, row by row, little endian:

- header: the color format in bits 0-4 (4 = true color, 5 = true color with alpha), the width in bits 10-20 and the height in bits 21-31
- pixel: RGB565 as 16 bits, followed by an alpha byte when the format has alpha
"""

import struct
from io import BytesIO
from typing import Optional

from PIL import Image

_TRUE_COLOR = 4
_TRUE_COLOR_ALPHA = 5
_MAX_SIZE = 2047  # the header has 11 bits for each side


def png_to_binary(data: bytes) -> bytes:
    """
    :param data: the content of a PNG file
    :return: the content of the binary image file, see `image_to_binary`
    """
    with Image.open(BytesIO(data)) as source:
        return image_to_binary(source)


def image_to_binary(source: Image.Image, alpha: Optional[bool] = None) -> bytes:
    """
    :param source: the image
    :param alpha: whether the pixels have an alpha byte. By default they have one when the image is not fully opaque.
    :return: the content of the binary image file
    """
    image = source.convert("RGBA")
    width, height = image.size
    if width > _MAX_SIZE or height > _MAX_SIZE:
        raise ValueError(f"The image is {width}x{height} pixels, but at most {_MAX_SIZE} are possible per side")

    rgba = image.tobytes()
    red, green, blue, opacity = rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4]
    colors = [((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b in zip(red, green, blue)]
    has_alpha = min(opacity) < 255 if alpha is None else alpha

    color_format = _TRUE_COLOR_ALPHA if has_alpha else _TRUE_COLOR
    result = bytearray(struct.pack("<I", height << 21 | width << 10 | color_format))
    if has_alpha:
        for color, a in zip(colors, opacity):
            result += struct.pack("<HB", color, a)
    else:
        result += struct.pack(f"<{len(colors)}H", *colors)
    return bytes(result)
