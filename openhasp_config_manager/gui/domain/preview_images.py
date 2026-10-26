"""
The images of the preview: which file an object's `src` means, and how to read the binary images (`.bin`) of openHASP, see
`processing/image_conversion.py` for the format. Qt-free.
"""

from pathlib import Path
from typing import Mapping, Optional, Tuple

_TRUE_COLOR = 4
_TRUE_COLOR_ALPHA = 5


def plate_file_name(src: str) -> Optional[str]:
    """:return: the file on the plate that `src` means (`L:/a.png` and `/a.png` are `a.png`), None for a URL or nothing"""
    if not isinstance(src, str):
        return None
    for prefix in ("L:/", "/"):
        if src.startswith(prefix):
            return src[len(prefix) :] or None
    return None


def find_image_file(src: str, files: Mapping[str, Path]) -> Optional[Path]:
    """
    :param src: the `src` of an object
    :param files: the image files of the device: their name on the plate -> the file
    :return: the file to show for `src`. A `.bin` that is not in the config is shown from the PNG it is converted from, see the
        `binary_images` variable.
    """
    name = plate_file_name(src)
    if name is None:
        return None
    if name in files:
        return files[name]
    if name.endswith(".bin"):
        return files.get(f"{name[:-4]}.png")
    return None


def decode_binary_image(data: bytes) -> Optional[Tuple[int, int, bytes]]:
    """
    :param data: the content of a binary image file: true color (RGB565), with or without alpha
    :return: width, height and the RGBA pixels (8 bits per channel), None if the file is something else
    """
    if len(data) < 4:
        return None
    header = int.from_bytes(data[:4], "little")
    color_format, width, height = header & 0x1F, (header >> 10) & 0x7FF, header >> 21
    has_alpha = color_format == _TRUE_COLOR_ALPHA
    if color_format not in (_TRUE_COLOR, _TRUE_COLOR_ALPHA) or width == 0 or height == 0:
        return None
    pixel_size = 3 if has_alpha else 2
    if len(data) != 4 + width * height * pixel_size:
        return None

    pixels = bytearray()
    for offset in range(4, len(data), pixel_size):
        color = data[offset] | data[offset + 1] << 8
        red, green, blue = (color >> 11) & 0x1F, (color >> 5) & 0x3F, color & 0x1F
        pixels += bytes(
            (
                (red << 3) | (red >> 2),
                (green << 2) | (green >> 4),
                (blue << 3) | (blue >> 2),
                data[offset + 2] if has_alpha else 255,
            )
        )
    return width, height, bytes(pixels)
