"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""


import pytest

from tests import TestBase
from tests.gui.preview_touch.helpers import center, lift, preview, widget


def QtCore_point(x, y):
    from PyQt6 import QtCore

    return QtCore.QPointF(x, y)


TABVIEW = {"page": 1, "id": 11, "obj": "tabview", "x": 0, "y": 0, "w": 300, "h": 200, "val": 0}


TABS = [{"page": 1, "id": 12 + n, "obj": "tab", "parentid": 11, "text": f"T{n}"} for n in range(3)]


def swipe(view, item, *points):
    """The finger touches at the first point (if it is not down yet), then is at each point for one read of the plate (20 ms)."""
    for point in points:
        view.finger(point, 0.0)
        item.read_swipe()


@pytest.mark.usefixtures("qapp")
class TestPreviewMessageBox(TestBase):
    BOX = {"page": 1, "id": 10, "obj": "msgbox", "w": 300, "text": "Hello", "options": ["Yes", "No"]}

    def test_a_pressed_button_looks_pressed_and_releasing_it_closes_the_box(self):
        view = preview(self.BOX)
        item = widget(view, 10)
        yes = center(item, item.button_rects()[0])

        view.finger(yes, 0.0)
        assert item.runtime.pressed_part == 0
        view._indev.release(yes)

        assert item.runtime.is_closed(item.key)
        assert not item.isVisible()

    def test_the_box_stays_if_the_finger_is_let_go_beside_the_buttons(self):
        view = preview(self.BOX)
        item = widget(view, 10)
        yes = center(item, item.button_rects()[0])
        text = item.mapToScene(QtCore_point(150, 10))

        view.finger(yes, 0.0)
        view.finger((text.x(), text.y()), 0.1)
        view._indev.release((text.x(), text.y()))

        assert item.isVisible()

    def test_the_button_under_the_finger_at_the_release_is_the_one_that_closes_the_box(self):
        view = preview(self.BOX)
        item = widget(view, 10)
        yes, no = (center(item, rect) for rect in item.button_rects())

        view.finger(yes, 0.0)
        view.finger(no, 0.1)
        assert item.runtime.pressed_part == 1
        view._indev.release(no)

        assert not item.isVisible()

    def test_the_text_of_the_box_does_not_close_it(self):
        view = preview(self.BOX)
        item = widget(view, 10)
        point = item.mapToScene(QtCore_point(150, 10))

        lift(view, point.x(), point.y())

        assert item.isVisible()

    def test_reset_brings_the_box_back(self):
        view = preview(self.BOX)
        item = widget(view, 10)
        lift(view, *center(item, item.button_rects()[0]))

        view.reset_interactions()

        assert widget(view, 10).isVisible()


@pytest.mark.usefixtures("qapp")
class TestPreviewTabview(TestBase):
    def test_releasing_a_tab_button_makes_its_tab_active(self):
        view = preview(TABVIEW, *TABS)
        item = widget(view, 11)

        lift(view, *center(item, item.button_rects()[2]))

        assert item.data["val"] == 2

    def test_a_pressed_tab_button_is_not_active_until_released(self):
        view = preview(TABVIEW, *TABS)
        item = widget(view, 11)
        second = center(item, item.button_rects()[1])

        view.finger(second, 0.0)
        assert item.data["val"] == 0
        assert item.runtime.pressed_part == 1
        view._indev.release(second)

        assert item.data["val"] == 1

    def test_the_indicator_moves_to_the_active_tab_in_the_anim_time(self):
        view = preview(TABVIEW, *TABS)
        item = widget(view, 11)

        lift(view, *center(item, item.button_rects()[2]))

        assert item._anim.duration() == 300
        # from the first tab (the animation runs in real time while the events are processed, so its start, not its current value)
        assert item._anim.startValue() == 0
        item.finish_animation()
        assert item.indicator_position == 2

    def test_a_tabview_with_anim_time_0_moves_the_indicator_at_once(self):
        view = preview({**TABVIEW, "anim_time": 0}, *TABS)
        item = widget(view, 11)

        lift(view, *center(item, item.button_rects()[1]))

        assert item._anim is None
        assert item.indicator_position == 1

    def test_swiping_the_content_past_the_middle_shows_the_next_tab(self):
        view = preview(TABVIEW, *TABS)
        item = widget(view, 11)

        swipe(view, item, *[(250 - 20 * n, 130) for n in range(10)], (70, 130))
        view._indev.release((70, 130))

        assert item.data["val"] == 1
        assert item._anim is not None
        item.finish_animation()

    def test_the_content_can_be_swiped_outside_of_the_tabview(self):
        view = preview({**TABVIEW, "x": 100}, *TABS)
        item = widget(view, 11)

        swipe(view, item, *[(350 - 25 * n, 130) for n in range(12)])
        view._indev.release((50, 130))

        assert item.data["val"] == 1
        item.finish_animation()

    def test_a_short_swipe_keeps_the_tab(self):
        view = preview(TABVIEW, *TABS)
        item = widget(view, 11)

        swipe(view, item, *[(250 - 10 * n, 130) for n in range(6)], (200, 130))
        view._indev.release((200, 130))

        assert item.data["val"] == 0

    def test_an_object_on_the_active_tab_is_touched_only_inside_of_the_tab(self):
        # GIVEN: a button on the second tab that reaches out of the tabview, and one on the first tab
        button = {"page": 1, "id": 20, "obj": "btn", "x": 250, "y": 50, "w": 100, "h": 50, "parentid": 13}
        hidden = {"page": 1, "id": 21, "obj": "btn", "x": 250, "y": 50, "w": 100, "h": 50, "parentid": 12}
        view = preview({**TABVIEW, "val": 1}, *TABS, button, hidden)

        # WHEN the finger is on the button inside of the tab
        view.finger((270, 62 + 75), 0.0)

        # THEN it is pressed, not the one of the hidden tab
        assert widget(view, 20).is_pressed
        view._indev.release((270, 62 + 75))

        # WHEN the finger is on the part of the button outside of the tabview
        view.finger((320, 62 + 75), 0.0)

        # THEN
        assert not widget(view, 20).is_pressed
        view._indev.release((320, 62 + 75))

    def test_switching_the_tab_shows_its_objects(self):
        button = {"page": 1, "id": 20, "obj": "btn", "x": 10, "y": 10, "w": 100, "h": 50, "parentid": 14}
        view = preview(TABVIEW, *TABS, button)
        item = widget(view, 11)
        assert not widget(view, 20).isVisible()

        lift(view, *center(item, item.button_rects()[2]))

        assert widget(view, 20).isVisible()
