"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""


import pytest

from openhasp_config_manager.gui.domain.roller_scroll import settled_option
from tests import TestBase
from tests.gui.preview_touch.helpers import BUTTON, DROPDOWN, lift, preview, widget


def drag(view, item, *points):
    """The finger touches at the first point (if it is not down yet), then is at each point for one read of the plate (20 ms)."""
    for point in points:
        view.finger(point, 0.0)
        item._scroll.tick()


ROLLER = {"page": 1, "id": 8, "obj": "roller", "x": 10, "y": 10, "w": 120, "rows": 3, "options": "A\nB\nC\nD\nE", "val": 1}


@pytest.mark.usefixtures("qapp")
class TestPreviewDropdown(TestBase):
    def test_touching_a_dropdown_opens_its_list_and_touching_it_again_closes_it(self):
        view = preview(DROPDOWN)
        item = widget(view, 6)

        lift(view, 20, 20)
        assert item.is_open
        assert item.zValue() > 0
        lift(view, 20, 20)

        assert not item.is_open
        assert item.zValue() == 0

    def test_the_dropdown_looks_pressed_while_the_finger_is_on_it(self):
        view = preview(DROPDOWN)

        view.finger((20, 20), 0.0)

        assert widget(view, 6).is_pressed
        view._indev.release((20, 20))

    def test_a_row_of_the_list_is_selected_on_release_and_the_list_closes(self):
        draft = dict(DROPDOWN)
        view = preview(draft)
        lift(view, 20, 20)
        # the list starts at 50, rows are 45 high
        view.finger((20, 50 + 45 * 2 + 5), 0.0)
        assert widget(view, 6).runtime.pressed_row == 2
        view._indev.release((20, 50 + 45 * 2 + 5))

        assert widget(view, 6).data["val"] == 2
        assert widget(view, 6).selected_text == "Three"
        assert not widget(view, 6).is_open
        assert draft["val"] == 1

    def test_a_row_is_not_selected_when_the_finger_leaves_the_list(self):
        view = preview(DROPDOWN)
        lift(view, 20, 20)

        view.finger((20, 60), 0.0)
        view.finger((400, 300), 0.1)
        view._indev.release((400, 300))

        assert widget(view, 6).data["val"] == 1
        assert widget(view, 6).runtime.pressed_row is None

    def test_a_press_somewhere_else_closes_the_list_without_changing_the_value(self):
        view = preview(DROPDOWN, {**BUTTON, "id": 7, "x": 300, "y": 200})
        lift(view, 20, 20)

        view.finger((310, 210), 0.0)
        view._indev.release((310, 210))

        assert not widget(view, 6).is_open
        assert widget(view, 6).data["val"] == 1

    def test_the_open_list_is_over_the_objects_below_it(self):
        view = preview(DROPDOWN, {**BUTTON, "id": 7, "x": 10, "y": 60, "toggle": True})
        lift(view, 20, 20)

        # the button is under the list: the touch selects a row and doesn't toggle the button
        lift(view, 20, 70)

        assert widget(view, 6).data["val"] == 0
        assert not widget(view, 7).is_toggled

    def test_dragging_the_list_scrolls_it_and_selects_nothing(self):
        view = preview({**DROPDOWN, "options": "\n".join("ABCDEFGHIJ"), "val": 0})
        item = widget(view, 6)
        lift(view, 20, 20)
        assert item.open_layout().scroll == 0

        # WHEN: the finger presses a row and drags the list up
        drag(view, item, (20, 200), (20, 195))
        assert item.runtime.pressed_row == 3
        drag(view, item, (20, 185), *[(20, 100)] * 10)

        # THEN: the drag unpressed the row and moved the rows with the finger (and the jump at the start)
        assert item.runtime.pressed_row is None
        assert item.open_layout().scroll == -110

        # WHEN
        view._indev.release((20, 100))

        # THEN: nothing is selected, the list stays open where it was dragged to
        assert item.data["val"] == 0
        assert item.is_open
        assert item.open_layout().scroll == -110

    def test_the_list_scrolls_no_further_than_its_last_row_and_opens_at_the_selected_row_again(self):
        view = preview({**DROPDOWN, "options": "\n".join("ABCDEFGHIJ"), "val": 0})
        item = widget(view, 6)
        lift(view, 20, 20)
        opened = item.open_layout()

        drag(view, item, (20, 250), (20, 230), *[(20, -2000)] * 3)
        view._indev.release((20, -2000))
        item._scroll.finish()

        assert item.open_layout().scroll == opened.h - opened.content_height

        # WHEN: closed and opened again
        lift(view, 20, 20)
        lift(view, 20, 20)

        # THEN
        assert item.open_layout().scroll == 0

    def test_the_list_opens_above_without_room_below_and_is_hit_there(self):
        view = preview({**DROPDOWN, "y": 280, "h": 30})
        lift(view, 20, 290)

        opened = widget(view, 6).open_layout()

        assert opened.y + opened.h == 280
        assert widget(view, 6).hit(widget(view, 6).mapFromScene(20, 200))


@pytest.mark.usefixtures("qapp")
class TestPreviewRoller(TestBase):
    def row_height(self, view):
        return widget(view, 8).row_height

    def test_a_click_on_a_row_selects_it_and_the_rows_move_to_it(self):
        draft = dict(ROLLER)
        view = preview(draft)
        row = self.row_height(view)

        # the row below the middle one (the middle one is the option 1)
        lift(view, 20, 10 + row * 2.5)

        item = widget(view, 8)
        assert item.data["val"] == 2
        # the rows start where they were, one row off, and animate to the new option (the animation runs in real time
        # while the events are processed, so its start, not its current value)
        assert item._anim.startValue() == pytest.approx(row)
        item.finish_animation()
        assert item._offset == 0
        assert draft["val"] == 1

    def test_dragging_moves_the_rows_and_letting_go_selects_the_nearest_option(self):
        view = preview(ROLLER)
        item = widget(view, 8)

        # the move that reaches the drag limit (10 pixels) counts twice, then the rows follow: 60 pixels and the jump of 10
        drag(view, item, (20, 60), (20, 50), (20, 40), (20, 0), (20, 0))
        assert item._offset == -70
        # the finger can leave the roller while it drags, and rests before it is let go (no throw)
        drag(view, item, (400, 0), *[(400, 0)] * 8)
        view._indev.release((400, 0))

        # 70 pixels up of rows of 45: the option after the next one is nearest to the middle
        assert item.data["val"] == 3
        item.finish_animation()

    def test_the_rows_move_in_the_anim_time_of_the_roller(self):
        view = preview({**ROLLER, "anim_time": 600})
        item = widget(view, 8)

        lift(view, 20, 10 + item.row_height * 2.5)

        assert item._anim.duration() == 600
        item.finish_animation()

    def test_a_roller_with_anim_time_0_moves_the_rows_at_once(self):
        view = preview({**ROLLER, "anim_time": 0})
        item = widget(view, 8)

        lift(view, 20, 10 + item.row_height * 2.5)

        assert item.data["val"] == 2
        assert item._anim is None
        assert item._offset == 0

    def test_a_flicked_roller_keeps_moving_after_it_is_let_go(self):
        view = preview({**ROLLER, "options": "\n".join("ABCDEFGHIJ"), "val": 0})
        item = widget(view, 8)
        drag(view, item, (20, 100), (20, 85), (20, 70), (20, 55))
        assert item._offset == -60
        assert settled_option(0, -60, item.row_height, 10, False) == 1

        # WHEN
        view._indev.release((20, 55))
        item._scroll.finish()

        # THEN: the throw moved the rows 43 pixels further (LVGL's integer math), and the option is selected when it ends
        assert item.data["val"] == settled_option(0, -103, item.row_height, 10, False) == 2
        item.finish_animation()

    def test_a_roller_stops_at_its_last_option(self):
        view = preview(ROLLER)
        item = widget(view, 8)
        drag(view, item, (20, 100), (20, 80), (20, -300), (20, -900))
        view._indev.release((20, -900))
        item._scroll.finish()

        assert item.data["val"] == 4
        item.finish_animation()

    def test_a_roller_in_infinite_mode_wraps_around(self):
        view = preview({**ROLLER, "mode": 1, "val": 4})
        item = widget(view, 8)
        # 10 pixels to start the drag, then a row up and the jump of the start (10)
        drag(view, item, (20, 100), (20, 90), *[(20, 90 - round(item.row_height) + 10)] * 10)
        view._indev.release((20, 0))
        item._scroll.finish()

        assert item.data["val"] == 0
        item.finish_animation()

    def test_the_selected_band_looks_pressed_while_touched(self):
        view = preview(ROLLER)

        view.finger((20, 60), 0.0)

        assert widget(view, 8).is_pressed
        view._indev.release((20, 60))
        widget(view, 8).finish_animation()
