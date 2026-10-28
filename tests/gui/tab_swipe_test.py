from openhasp_config_manager.gui.domain.tab_swipe import TabSwipe, predicted_move
from tests import TestBase


def _swipe(swipe: TabSwipe, *points):
    swipe.press(*points[0])
    for point in points[1:]:
        swipe.read(*point)


class TestTabSwipe(TestBase):
    def test_the_predicted_move_is_the_move_slowing_down_by_a_fifth_per_read(self):
        assert predicted_move(20) == 20 + 16 + 12 + 9 + 7 + 5 + 4 + 3 + 2 + 1
        assert predicted_move(-20) == -79
        assert predicted_move(0) == 0

    def test_the_read_that_reaches_the_drag_limit_does_not_move_the_content(self):
        swipe = TabSwipe(0, 3, 300)

        _swipe(swipe, (250, 100), (230, 100))

        assert swipe.dragging is True
        assert swipe.shift == 0

        swipe.read(210, 100)

        assert swipe.shift == -20

    def test_a_slow_swipe_shows_the_next_tab_only_past_the_middle(self):
        short = TabSwipe(0, 3, 300)
        _swipe(short, (250, 100), *[(250 - 20 * n, 100) for n in range(1, 9)], (90, 100))
        far = TabSwipe(0, 3, 300)
        _swipe(far, (250, 100), *[(250 - 20 * n, 100) for n in range(1, 10)], (70, 100))

        assert short.shift == -140
        assert short.release(0, 300) == 0
        assert far.shift == -160
        assert far.release(0, 300) == 1

    def test_a_flick_shows_the_tab_next_to_it_before_the_middle(self):
        flicked = TabSwipe(1, 3, 300)
        _swipe(flicked, (50, 100), *[(50 + 20 * n, 100) for n in range(1, 6)])
        rested = TabSwipe(1, 3, 300)
        _swipe(rested, (50, 100), *[(50 + 20 * n, 100) for n in range(1, 6)], (150, 100))

        # 80 moved, and 79 predicted for the flick: past the middle (150)
        assert flicked.shift == rested.shift == 80
        assert flicked.release(0, 300) == 0
        assert rested.release(0, 300) == 1

    def test_the_first_tab_can_not_be_swiped_away_from_the_edge(self):
        swipe = TabSwipe(0, 3, 300)

        _swipe(swipe, (50, 100), *[(50 + 30 * n, 100) for n in range(1, 8)])

        assert swipe.shift == 0
        assert swipe.release(0, 300) == 0

    def test_a_swipe_up_does_not_move_the_content(self):
        swipe = TabSwipe(1, 3, 300)

        _swipe(swipe, (150, 150), (148, 130), (146, 110), (146, 90))

        assert swipe.shift == 0
        assert swipe.release(0, 300) == 1

    def test_a_touch_without_drag_shows_no_other_tab(self):
        swipe = TabSwipe(1, 3, 300)

        _swipe(swipe, (150, 150), (145, 152))

        assert swipe.release(0, 300) is None
