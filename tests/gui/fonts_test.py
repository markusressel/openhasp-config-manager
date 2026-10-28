import pytest

from openhasp_config_manager.gui.domain.fonts import DEFAULT_FONT, FontKind, PlateFont, font_size, resolve_font


@pytest.mark.parametrize(
    "value, expected",
    [
        # the sizes of the fonts built into the firmware
        (12, PlateFont(12, FontKind.BUILT_IN)),
        ("32", PlateFont(32, FontKind.BUILT_IN)),
        (24.0, PlateFont(24, FontKind.BUILT_IN)),
        # the ids of fonts: 0 is the small font, 1 to 3 the default font, the others are not set
        (0, PlateFont(16, FontKind.BUILT_IN)),
        (3, DEFAULT_FONT),
        (5, DEFAULT_FONT),
        # the pixel font
        (8, PlateFont(8, FontKind.PIXEL)),
        # any other size is drawn from the TrueType font of the firmware
        (9, PlateFont(9, FontKind.TRUETYPE)),
        ("25", PlateFont(25, FontKind.TRUETYPE)),
        (40, PlateFont(40, FontKind.TRUETYPE)),
        # a font file that is not on the plate doesn't change the font
        ("arial_20", DEFAULT_FONT),
        ("robotocondensed_regular_16_latin1", DEFAULT_FONT),
        # e.g. a template that is not rendered
        ("{{ content.text_size }}", DEFAULT_FONT),
        (None, DEFAULT_FONT),
    ],
)
def test_the_font_is_picked_like_on_the_plate(value, expected):
    assert resolve_font(value) == expected


def test_a_font_file_on_the_plate_is_used_in_the_size_at_the_end_of_its_name():
    files = ["arial.ttf", "mono_16.bin"]

    assert resolve_font("arial20", files) == PlateFont(20, FontKind.FILE, "arial.ttf")
    assert resolve_font("arial_20", files) == PlateFont(20, FontKind.FILE, "arial.ttf")
    assert resolve_font("mono_16", files) == PlateFont(16, FontKind.FILE, "mono_16.bin")


def test_a_value_that_does_not_change_the_font_keeps_the_default():
    small = PlateFont(16, FontKind.BUILT_IN)

    assert resolve_font(None, default=small) == small
    assert font_size("arial_20", default=17) == 17
