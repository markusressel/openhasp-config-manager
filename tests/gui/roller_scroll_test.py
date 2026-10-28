from openhasp_config_manager.gui.domain.roller_scroll import clicked_option, settled_option
from tests import TestBase


class TestRollerScroll(TestBase):
    def test_let_go_the_nearest_option_is_in_the_middle(self):
        # rows of 45: moving the rows up by 100 pixels shows the option 2 rows further
        assert settled_option(selected=1, offset=-100, row=45, count=10, infinite=False) == 3
        assert settled_option(selected=3, offset=50, row=45, count=10, infinite=False) == 2
        assert settled_option(selected=3, offset=10, row=45, count=10, infinite=False) == 3

    def test_a_normal_roller_stops_at_its_ends(self):
        assert settled_option(selected=1, offset=500, row=45, count=4, infinite=False) == 0
        assert settled_option(selected=1, offset=-500, row=45, count=4, infinite=False) == 3

    def test_an_infinite_roller_wraps_around(self):
        assert settled_option(selected=1, offset=500, row=45, count=4, infinite=True) == (1 - 11) % 4
        assert settled_option(selected=3, offset=-45, row=45, count=4, infinite=True) == 0

    def test_a_click_selects_the_row_that_was_touched(self):
        # a roller of 135 pixels with rows of 45 and the option 2 in the middle: rows at 0..45 (1), 45..90 (2), 90..135 (3)
        assert clicked_option(2, y=10, height=135, offset=0, row=45, count=6, infinite=False) == 1
        assert clicked_option(2, y=60, height=135, offset=0, row=45, count=6, infinite=False) == 2
        assert clicked_option(2, y=120, height=135, offset=0, row=45, count=6, infinite=False) == 3

    def test_a_click_beyond_the_options_takes_the_first_or_last(self):
        assert clicked_option(0, y=10, height=135, offset=0, row=45, count=3, infinite=False) == 0
        assert clicked_option(2, y=120, height=135, offset=0, row=45, count=3, infinite=False) == 2

    def test_a_click_in_an_infinite_roller_wraps_around(self):
        assert clicked_option(0, y=10, height=135, offset=0, row=45, count=3, infinite=True) == 2

    def test_nothing_is_clicked_in_a_roller_without_options(self):
        assert clicked_option(0, y=10, height=135, offset=0, row=45, count=0, infinite=False) is None
