"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""

import math

import pytest

from tests import TestBase
from tests.gui.preview_touch.helpers import DROPDOWN, lift, preview, tap, widget


@pytest.mark.usefixtures("qapp")
class TestPreviewColorPicker(TestBase):
    PICKER = {"page": 1, "id": 13, "obj": "cpicker", "x": 10, "y": 10, "w": 200, "h": 200, "color": "#FF0000"}

    def test_the_color_follows_the_finger_on_the_ring(self):
        view = preview(self.PICKER)
        item = widget(view, 13)

        # the ring is the outer 20 pixels: at the right edge of the circle, 3 o'clock
        view.finger((10 + 200 - 10, 110), 0.0)
        view._indev.release((10 + 200 - 10, 110))

        # the colors start at 6 o'clock (red); 3 o'clock is a quarter turn on, the angle counts clockwise from there
        assert item.data["color"] != "#FF0000"
        assert abs(item.color.hue() - 90) <= 1
        # the knob is where the finger is (it was drawn mirrored, at 9 o'clock)
        knob = item.mapToScene(item.knob_center())
        assert abs(knob.x() - 200) <= 2 and abs(knob.y() - 110) <= 2

    @pytest.mark.parametrize("finger", [(110, 200), (110, 20), (20, 110), (180, 50)])
    def test_the_knob_follows_the_finger_around_the_ring(self, finger):
        view = preview(self.PICKER)
        item = widget(view, 13)

        view.finger(finger, 0.0)
        view._indev.release(finger)

        # the knob is on the ring, in the direction of the finger
        knob = item.mapToScene(item.knob_center())
        center = item.mapToScene(item.obj_rect.center())
        finger_angle = math.atan2(finger[1] - center.y(), finger[0] - center.x())
        knob_angle = math.atan2(knob.y() - center.y(), knob.x() - center.x())
        assert abs(math.remainder(finger_angle - knob_angle, math.tau)) < math.radians(2)

    def test_the_middle_of_the_disc_changes_nothing_and_a_long_press_there_switches_the_mode(self):
        view = preview(self.PICKER)
        item = widget(view, 13)

        view.finger((110, 110), 0.0)
        view._indev.tick(0.5)
        view._indev.release((110, 110))

        assert item.data["color"] == "#FF0000"
        assert item.mode == "saturation"

    def test_a_finger_that_moves_in_the_middle_of_the_disc_rests_anew(self):
        view = preview(self.PICKER)
        item = widget(view, 13)

        view.finger((110, 110), 0.0)
        view.finger((116, 110), 0.3)
        view._indev.tick(0.5)

        assert item.mode == "hue"

        view._indev.tick(0.71)

        assert item.mode == "saturation"

    def test_a_color_picker_with_mode_fixed_keeps_its_mode(self):
        view = preview({**self.PICKER, "mode_fixed": 1})
        item = widget(view, 13)

        view.finger((110, 110), 0.0)
        view._indev.tick(1.0)

        assert item.mode == "hue"

    def test_after_the_mode_changed_the_finger_changes_nothing_until_it_is_let_go(self):
        view = preview(self.PICKER)
        item = widget(view, 13)
        view.finger((110, 110), 0.0)
        view._indev.tick(0.5)

        view.finger((110, 205), 0.6)

        assert item.data["color"] == "#FF0000"

    def test_a_double_click_puts_the_hue_back_to_0(self):
        view = preview({**self.PICKER, "color": "#00FF00"})
        item = widget(view, 13)

        tap(view, 110, 110, now=0.0)
        view.finger((110, 110), 0.3)
        # the finger changes nothing until it is let go
        view.finger((205, 110), 0.35)
        view._indev.release((205, 110))

        assert item.data["color"] == "#FF0000"

    def test_two_presses_further_apart_are_no_double_click(self):
        view = preview({**self.PICKER, "color": "#00FF00"})
        item = widget(view, 13)

        tap(view, 110, 110, now=0.0)
        tap(view, 110, 110, now=0.5)

        assert item.data["color"] == "#00FF00"

    def test_a_finger_that_rests_on_a_bar_switches_the_mode_after_800_ms(self):
        view = preview({**self.PICKER, "w": 200, "h": 40})
        item = widget(view, 13)

        view.finger((20, 30), 0.0)
        view._indev.tick(0.6)

        assert item.mode == "hue"

        view._indev.tick(0.81)

        assert item.mode == "saturation"

    def test_a_touch_outside_the_circle_is_not_a_touch(self):
        view = preview(self.PICKER)

        view.finger((12, 12), 0.0)

        assert view._indev.active is None

    def test_the_finger_can_leave_the_ring_while_dragging(self):
        view = preview(self.PICKER)
        item = widget(view, 13)

        view.finger((200, 110), 0.0)
        view.finger((450, 300), 0.1)
        view._indev.release((450, 300))

        assert item.data["color"] != "#FF0000"


@pytest.mark.usefixtures("qapp")
class TestPreviewSelectorGroups(TestBase):
    def test_a_dropdown_makes_the_group_follow(self):
        dropdown = {**DROPDOWN, "groupid": 3, "options": "A\nB\nC", "val": 0}
        slider = {
            "page": 1,
            "id": 5,
            "obj": "slider",
            "x": 10,
            "y": 200,
            "w": 200,
            "h": 20,
            "min": 0,
            "max": 100,
            "val": 0,
            "groupid": 3,
        }
        view = preview(dropdown, slider)
        view.set_group_objects(lambda: [dropdown, slider])
        lift(view, 20, 20)

        lift(view, 20, 50 + 45 * 2 + 5)

        assert widget(view, 5).data["val"] == 100
