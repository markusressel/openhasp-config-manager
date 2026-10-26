from io import BytesIO
from typing import List, Tuple

from PIL import Image


def png(size: Tuple[int, int], pixels: List[tuple], mode: str = "RGB") -> bytes:
    """:return: the content of a PNG file of the given size, with the pixels row by row"""
    image = Image.new(mode, size)
    image.putdata(pixels)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
