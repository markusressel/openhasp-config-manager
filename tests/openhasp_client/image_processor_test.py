import io
import struct
from typing import List, Tuple

import pytest
from PIL import Image

from openhasp_config_manager.openhasp_client.image_processor import ImageFit, OpenHaspImageProcessor

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)


@pytest.fixture
def wide_image(tmp_path) -> str:
    """40x20: red on the left, blue on the right, with a green stripe at each side (cut off when it covers a square)"""
    image = Image.new("RGB", (40, 20), RED)
    image.paste(BLUE, (20, 0, 40, 20))
    image.paste(GREEN, (0, 0, 4, 20))
    image.paste(GREEN, (36, 0, 40, 20))
    path = tmp_path / "wide.png"
    image.save(path)
    return str(path)


async def _convert(image: str, size, **kwargs) -> Tuple[int, int, List[List[Tuple[int, int, int]]]]:
    """:return: the width, the height and the rows of pixels of the binary image"""
    out = io.BytesIO()
    await OpenHaspImageProcessor().image_to_rgb565(in_image=image, out_image=out, size=size, **kwargs)
    data = out.getvalue()
    header = int.from_bytes(data[:4], "little")
    width, height = (header >> 10) & 0x7FF, (header >> 21) & 0x7FF
    pixels = [struct.unpack_from("<H", data, 4 + i * 2)[0] for i in range(width * height)]
    rgb = [((p >> 11) * 255 // 31, ((p >> 5) & 0x3F) * 255 // 63, (p & 0x1F) * 255 // 31) for p in pixels]
    return width, height, [rgb[y * width : (y + 1) * width] for y in range(height)]


def _color(pixel: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """:return: the pure color the pixel is closest to (the resampling blends the edges)"""
    return min((RED, GREEN, BLUE, BLACK), key=lambda color: sum((a - b) ** 2 for a, b in zip(pixel, color)))


async def test_by_default_the_image_covers_the_size_and_its_edges_are_cut_off(wide_image):
    # WHEN
    width, height, rows = await _convert(wide_image, (10, 10))

    # THEN: the middle 20x20, scaled to 10x10: no green
    assert (width, height) == (10, 10)
    assert [_color(pixel) for pixel in rows[5]] == [RED] * 5 + [BLUE] * 5


async def test_contain_fits_the_whole_image_with_black_bars(wide_image):
    # WHEN
    width, height, rows = await _convert(wide_image, (40, 40), fit=ImageFit.CONTAIN)

    # THEN
    assert (width, height) == (40, 40)
    assert {_color(pixel) for pixel in rows[2] + rows[37]} == {BLACK}
    assert [_color(rows[20][x]) for x in (1, 10, 30, 38)] == [GREEN, RED, BLUE, GREEN]


async def test_fill_stretches_the_image(wide_image):
    # WHEN
    width, height, rows = await _convert(wide_image, (20, 40), fit=ImageFit.FILL)

    # THEN: everything, no bars
    assert (width, height) == (20, 40)
    assert [_color(rows[y][x]) for y, x in ((1, 0), (20, 5), (38, 15), (20, 19))] == [GREEN, RED, BLUE, GREEN]


async def test_fitscreen_stretches_the_image(wide_image):
    # WHEN
    stretched = await _convert(wide_image, (20, 40), fitscreen=True)

    # THEN
    assert stretched == await _convert(wide_image, (20, 40), fit=ImageFit.FILL)


async def test_a_side_without_a_size_keeps_the_size_of_the_image(wide_image):
    # WHEN
    width, height, _ = await _convert(wide_image, (None, None))

    # THEN
    assert (width, height) == (40, 20)


async def test_a_smaller_image_is_scaled_up_since_the_plate_would_repeat_it(wide_image):
    # WHEN
    width, height, _ = await _convert(wide_image, (80, 40))

    # THEN
    assert (width, height) == (80, 40)
