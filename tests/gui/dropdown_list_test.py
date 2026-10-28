from openhasp_config_manager.gui.domain.dropdown_list import (
    DIR_DOWN,
    DIR_LEFT,
    DIR_RIGHT,
    DIR_UP,
    default_max_height,
    open_list,
    row_height,
    scroll_to,
)
from tests import TestBase

SCREEN = (480, 320)


def layout(box, count=3, font=24, direction=DIR_DOWN, max_height=240, selected=0, widest=40.0):
    return open_list(box, count, row_height(font), widest, direction, max_height, selected, SCREEN)


class TestDropdownList(TestBase):
    def test_rows_are_as_high_as_measured_on_the_plate(self):
        assert [row_height(size) for size in (12, 16, 24)] == [31, 36, 45]
        assert default_max_height(320) == 240

    def test_the_list_opens_below_with_the_width_of_the_dropdown(self):
        # measured: dd_open_short, three rows under a dropdown at 260, 10 of 200 x 40
        opened = layout((260, 10, 200, 40), selected=2)

        assert (opened.x, opened.y, opened.w, opened.h) == (260, 50, 200, 134)
        assert opened.direction == DIR_DOWN
        assert opened.scroll == 0

    def test_a_long_list_is_cut_at_the_max_height_and_scrolled_to_the_selected_row(self):
        # measured: dd_open_default, seven rows of 45 under the dropdown, the second one selected
        opened = layout((10, 10, 200, 40), count=7, selected=1)

        assert opened.h == 240
        assert opened.scrolls
        assert opened.scroll == 0
        assert opened.thumb() == (3, 178)

    def test_the_last_rows_are_scrolled_into_view(self):
        # measured: dd_open_styled, four rows of 36 in 120 pixels, the third selected: the list ends with the last row
        opened = layout((10, 10, 220, 35), count=4, font=16, max_height=120, selected=2)

        assert (opened.y, opened.h, opened.scroll) == (45, 120, -23)
        assert opened.row_top(2) == 49
        assert opened.thumb() == (21, 96)

    def test_without_room_below_the_list_opens_above(self):
        # measured: dd_open_bottom, five rows over a dropdown at 140, 230
        opened = layout((140, 230, 200, 40), count=5, selected=3)

        assert opened.direction == DIR_UP
        assert (opened.y, opened.h) == (6, 224)

    def test_the_list_is_cut_at_the_screen_if_neither_side_has_room(self):
        opened = layout((10, 100, 100, 100), count=7, max_height=1000)

        # more room below (121 pixels, like LVGL counts it from the last pixel of the dropdown) than above (100)
        assert opened.direction == DIR_DOWN
        assert (opened.y, opened.h) == (200, 121)

    def test_a_dropdown_that_opens_up_goes_down_if_there_is_more_room(self):
        opened = layout((10, 10, 100, 40), count=3, direction=DIR_UP)

        assert opened.direction == DIR_DOWN
        assert opened.y == 50

    def test_the_list_beside_the_dropdown_is_as_wide_as_its_options(self):
        # measured: dd_open_direction, "Three" is 53.66 pixels wide at font 24 and the list 66
        right = layout((140, 120, 160, 40), direction=DIR_RIGHT, widest=53.66)
        left = layout((200, 120, 160, 40), direction=DIR_LEFT, widest=53.66)

        assert (right.x, right.y, right.w, right.h) == (300, 120, 66, 134)
        assert (left.x, left.w) == (200 - 66, 66)

    def test_the_list_beside_the_dropdown_is_moved_up_to_stay_on_the_screen(self):
        opened = layout((10, 280, 100, 30), direction=DIR_RIGHT)

        assert opened.y + opened.h == 320

    def test_a_dropdown_with_long_options_gets_a_wider_list(self):
        assert layout((10, 10, 100, 40), widest=200).w == 212

    def test_the_row_at_a_point_includes_what_is_beyond_the_list(self):
        opened = layout((10, 10, 200, 40), count=3)

        assert [opened.row_at(y) for y in (0, 50, 94, 95, 140, 300)] == [0, 0, 0, 1, 2, 2]
        assert opened.contains((20, 60))
        assert not opened.contains((20, 40))
        assert not opened.contains((300, 60))

    def test_scroll_to_centers_the_selected_row_within_the_ends(self):
        assert scroll_to(selected=3, row=45, count=10, height=240) == -45 * 3 + 97
        assert scroll_to(selected=0, row=45, count=10, height=240) == 0
        assert scroll_to(selected=9, row=45, count=10, height=240) == 240 - 449
