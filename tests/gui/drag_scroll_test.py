from openhasp_config_manager.gui.domain.drag_scroll import DragScroll
from tests import TestBase


def _drag(scroll: DragScroll, *ys: int):
    scroll.press(ys[0])
    for y in ys[1:]:
        scroll.read(y)


class TestDragScroll(TestBase):
    def test_a_finger_that_moves_less_than_the_drag_limit_does_not_drag(self):
        scroll = DragScroll(0, -500, 500)

        _drag(scroll, 100, 104, 109, 100)

        assert scroll.position == 0
        assert scroll.dragging is False
        assert scroll.release() is False

    def test_the_drag_starts_with_a_jump_and_then_follows_the_finger(self):
        scroll = DragScroll(0, -500, 500)
        scroll.press(100)
        scroll.read(106)

        # WHEN: the move that reaches the drag limit
        started = scroll.read(112)

        # THEN: the whole way so far, and that move once more (LVGL adds the sum and the move of the read)
        assert started is True
        assert scroll.position == 12 + 6

        # WHEN
        scroll.read(120)

        # THEN
        assert scroll.position == 18 + 8

    def test_the_position_stops_at_the_ends_and_follows_back_at_once(self):
        scroll = DragScroll(0, -30, 30)

        _drag(scroll, 100, 120, 160, 200)

        assert scroll.position == 30

        # WHEN: back up: it moves from the end, not from where the finger would have taken it
        scroll.read(190)

        # THEN
        assert scroll.position == 20

    def test_a_throw_slows_down_and_ends_the_drag(self):
        scroll = DragScroll(0, -1000, 1000)
        _drag(scroll, 100, 120, 140, 160, 180)
        released_at = scroll.position

        # WHEN
        ended = scroll.release()
        steps = 1
        while scroll.throw_step():
            steps += 1

        # THEN: it moved on after the finger was let go, slower every read, and ended by itself
        assert ended is False
        assert scroll.position > released_at
        assert 3 < steps < 30
        assert scroll.dragging is False

    def test_a_throw_ends_at_an_end(self):
        scroll = DragScroll(0, -1000, 70)
        _drag(scroll, 100, 120, 140, 160)

        scroll.release()
        while scroll.throw_step():
            pass

        assert scroll.position == 70

    def test_a_finger_that_rests_before_it_is_let_go_does_not_throw(self):
        scroll = DragScroll(0, -1000, 1000)
        _drag(scroll, 100, 120, 140, 160, *[160] * 10)
        position = scroll.position

        # WHEN
        ended = scroll.release()

        # THEN
        assert ended is True
        assert scroll.position == position

    def test_a_new_touch_stops_a_throw(self):
        scroll = DragScroll(0, -1000, 1000)
        _drag(scroll, 100, 130, 160, 190)
        scroll.release()

        # WHEN
        ended = scroll.stop()

        # THEN
        assert ended is True
        assert scroll.throw_step() is False
