import struct
import pytest

from openhasp_config_manager.processing.image_conversion import png_to_binary
from tests.png import png


def test_opaque_image_is_true_color_rgb565():
    data = png((2, 1), [(255, 0, 0), (0, 255, 0)])

    result = png_to_binary(data)

    header, red, green = struct.unpack("<IHH", result)
    assert header & 0x1F == 4
    assert (header >> 10) & 0x7FF == 2
    assert header >> 21 == 1
    assert red == 0xF800
    assert green == 0x07E0
    assert len(result) == 4 + 2 * 2


def test_image_with_transparency_has_an_alpha_byte_per_pixel():
    data = png((2, 1), [(0, 0, 255, 255), (255, 255, 255, 0)], mode="RGBA")

    result = png_to_binary(data)

    header = struct.unpack_from("<I", result)[0]
    assert header & 0x1F == 5
    assert struct.unpack_from("<HB", result, 4) == (0x001F, 255)
    assert struct.unpack_from("<HB", result, 7) == (0xFFFF, 0)
    assert len(result) == 4 + 2 * 3


def test_fully_opaque_rgba_image_has_no_alpha_bytes():
    data = png((1, 1), [(0, 0, 255, 255)], mode="RGBA")

    assert len(png_to_binary(data)) == 4 + 2


def test_rows_follow_each_other():
    data = png((1, 2), [(255, 0, 0), (0, 0, 255)])

    header, top, bottom = struct.unpack("<IHH", png_to_binary(data))

    assert header >> 21 == 2
    assert (top, bottom) == (0xF800, 0x001F)


def test_image_too_large_for_the_header_is_an_error():
    data = png((2048, 1), [(0, 0, 0)] * 2048)

    with pytest.raises(ValueError, match="2048x1"):
        png_to_binary(data)


def test_alpha_can_be_forced_either_way():
    from PIL import Image

    from openhasp_config_manager.processing.image_conversion import image_to_binary

    image = Image.new("RGBA", (1, 1), (0, 0, 255, 0))

    assert len(image_to_binary(image, alpha=False)) == 4 + 2
    assert len(image_to_binary(Image.new("RGB", (1, 1)), alpha=True)) == 4 + 3
