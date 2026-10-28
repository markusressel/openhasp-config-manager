from openhasp_config_manager.gui.domain.lvgl_colors import button_colors, darken, lighten, mix, parse_hex, to_display, to_hex
from tests import TestBase

# the theme colors of the plate the preview was measured on (`color1` and `color2`)
PRIMARY, SECONDARY = "#00b6ff", "#ff9962"


def assert_close(color, measured: str, tolerance: int = 2):
    """The screenshots of the plate are converted from RGB565, so a channel may be off by a step."""
    difference = max(abs(a - b) for a, b in zip(color, parse_hex(measured)))
    assert difference <= tolerance, f"{to_hex(color)} is not {measured}"


class TestLvglColors(TestBase):
    def test_a_display_color_keeps_the_steps_of_rgb565(self):
        assert to_display((255, 255, 255)) == (255, 255, 255)
        assert to_display((0, 0, 0)) == (0, 0, 0)
        # 0x88 is 17 of 31 steps in red and blue and 34 of 63 in green, filled up again with the high bits
        assert to_hex(to_display((0x88, 0x88, 0x88))) == "#8C8A8C"

    def test_mix_takes_the_amount_of_the_first_color(self):
        assert mix((255, 255, 255), (0, 0, 0), 255) == (255, 255, 255)
        assert mix((255, 255, 255), (0, 0, 0), 0) == (0, 0, 0)
        assert lighten((0, 0, 0), 255) == (255, 255, 255)
        assert darken((255, 255, 255), 255) == (0, 0, 0)

    def test_the_normal_and_checked_colors_are_the_ones_measured_on_the_plate(self):
        # the defaults of a button in `button.py` were measured: the formulas of the theme have to give them
        colors = button_colors(PRIMARY, SECONDARY)

        assert_close(colors.normal[0], "#4ACAFF")
        assert_close(colors.normal[1], "#0081B4")
        assert_close(colors.checked[0], "#FF9962")
        assert_close(colors.checked[1], "#623C29")

    def test_a_pressed_button_is_closer_to_the_theme_color_at_the_top_and_darker_at_the_bottom_than_a_normal_one(self):
        colors = button_colors(PRIMARY, SECONDARY)

        # lighten by 10 % instead of 30 %, darken by 50 % instead of 30 %
        assert colors.pressed[0][0] < colors.normal[0][0]
        assert colors.pressed[1][1] < colors.normal[1][1]
        # a pressed checked button is darker than a checked one
        assert sum(colors.checked_pressed[0]) < sum(colors.checked[0])
        assert sum(colors.checked_pressed[1]) < sum(colors.checked[1])

    def test_the_pressed_colors_of_the_theme_written_down_in_the_widgets(self):
        # the constants the preview uses, computed from the theme formulas (see `BUTTON_DEFAULTS`)
        colors = button_colors(PRIMARY, SECONDARY)

        assert to_hex(colors.pressed[0]) == "#18BEFF"
        assert to_hex(colors.pressed[1]) == "#005D84"
        assert to_hex(colors.checked_pressed[0]) == "#CE7952"
        assert to_hex(colors.checked_pressed[1]) == "#523021"
