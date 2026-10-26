from pathlib import Path

from openhasp_config_manager.gui.domain.preview_images import decode_binary_image, find_image_file, plate_file_name
from openhasp_config_manager.processing.image_conversion import png_to_binary
from tests.png import png


def test_plate_file_name():
    assert plate_file_name("L:/a_b.png") == "a_b.png"
    assert plate_file_name("/a.png") == "a.png"
    assert plate_file_name("http://192.168.2.10:20000/abc") is None
    assert plate_file_name("L:/") is None
    assert plate_file_name(None) is None


def test_find_image_file():
    files = {"a.png": Path("x/a.png"), "b.bin": Path("x/b.bin"), "c.png": Path("x/c.png")}

    assert find_image_file("L:/a.png", files) == Path("x/a.png")
    assert find_image_file("L:/b.bin", files) == Path("x/b.bin")
    # converted on deploy: the config only has the PNG
    assert find_image_file("L:/c.bin", files) == Path("x/c.png")
    assert find_image_file("L:/d.png", files) is None
    assert find_image_file("L:/d.bin", files) is None
    assert find_image_file("http://host/c.png", files) is None


def test_binary_image_without_alpha_is_decoded():
    data = png_to_binary(png((2, 1), [(255, 0, 0), (0, 0, 255)]))

    assert decode_binary_image(data) == (2, 1, bytes([255, 0, 0, 255, 0, 0, 255, 255]))


def test_binary_image_with_alpha_is_decoded():
    data = png_to_binary(png((2, 1), [(0, 255, 0, 255), (255, 255, 255, 0)], mode="RGBA"))

    assert decode_binary_image(data) == (2, 1, bytes([0, 255, 0, 255, 255, 255, 255, 0]))


def test_other_files_are_not_binary_images():
    valid = png_to_binary(png((1, 1), [(0, 0, 0)]))

    assert decode_binary_image(b"") is None
    assert decode_binary_image(b"\x89PNG\r\n\x1a\n") is None
    assert decode_binary_image(valid[:-1]) is None
    # width 0
    assert decode_binary_image(bytes([4, 0, 0, 0, 0, 0])) is None
    # another color format (indexed)
    assert decode_binary_image(bytes([7, 0x04, 0x20, 0]) + bytes(4)) is None
