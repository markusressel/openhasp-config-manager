from openhasp_config_manager.gui.domain.interaction import (
    LONG_PRESS_REPEAT_TIME,
    LONG_PRESS_TIME,
    Indev,
    RuntimeState,
    is_clickable,
)
from openhasp_config_manager.gui.domain.touch_actions import action_commands, page_command
from openhasp_config_manager.gui.domain.touch_groups import group_values, value_range
from openhasp_config_manager.gui.domain.touch_values import (
    ArcDrag,
    arc_last_angle,
    arc_value,
    c_div,
    lv_map,
    lvgl_atan2,
    slider_value,
)
from tests import TestBase


class FakeTarget:
    """What the input device needs of an object, recording what it was told."""

    def __init__(self, name: str, keeps_press: bool = False, area=(0, 0, 10, 10)):
        self.name = name
        self.keeps_press = keeps_press
        self.area = area
        self.calls = []

    def on_press(self, point):
        self.calls.append("press")

    def on_pressing(self, point):
        self.calls.append("pressing")

    def on_release(self, point, short_click):
        self.calls.append(f"release short={short_click}")

    def on_press_lost(self):
        self.calls.append("lost")

    def on_long_press(self):
        self.calls.append("long")

    def on_long_press_repeat(self):
        self.calls.append("repeat")

    def contains(self, point) -> bool:
        x, y, w, h = self.area
        return x <= point[0] < x + w and y <= point[1] < y + h


def indev_of(*targets: FakeTarget) -> Indev:
    return Indev(lambda point: next((target for target in targets if target.contains(point)), None))


class TestIndev(TestBase):
    def test_a_finger_presses_the_object_under_it_and_releases_it(self):
        first = FakeTarget("first")
        indev = indev_of(first)

        indev.press((5, 5), now=0)
        indev.release((5, 5))

        assert first.calls == ["press", "pressing", "release short=True"]

    def test_a_finger_on_nothing_presses_nothing(self):
        indev = indev_of(FakeTarget("first"))

        indev.press((50, 50), now=0)
        indev.release((50, 50))

        assert indev.active is None

    def test_leaving_an_object_loses_the_press_and_nothing_is_released(self):
        first = FakeTarget("first")
        indev = indev_of(first)
        indev.press((5, 5), now=0)

        indev.press((50, 5), now=0.1)
        indev.release((50, 5))

        assert first.calls == ["press", "pressing", "lost"]

    def test_moving_onto_another_object_presses_that_one(self):
        first, second = FakeTarget("first"), FakeTarget("second", area=(20, 0, 10, 10))
        indev = indev_of(first, second)
        indev.press((5, 5), now=0)

        indev.press((25, 5), now=0.1)
        indev.release((25, 5))

        assert first.calls == ["press", "pressing", "lost"]
        assert second.calls == ["press", "pressing", "release short=True"]

    def test_coming_back_to_an_object_presses_it_again(self):
        first = FakeTarget("first")
        indev = indev_of(first)
        indev.press((5, 5), now=0)
        indev.press((50, 5), now=0.1)

        indev.press((5, 5), now=0.2)

        assert first.calls == ["press", "pressing", "lost", "press", "pressing"]

    def test_an_object_that_keeps_the_press_is_released_wherever_the_finger_is(self):
        switch = FakeTarget("switch", keeps_press=True)
        indev = indev_of(switch)
        indev.press((5, 5), now=0)

        indev.press((50, 50), now=0.1)
        indev.release((50, 50))

        assert switch.calls == ["press", "pressing", "pressing", "release short=True"]

    def test_a_finger_that_rests_long_enough_long_presses_and_repeats(self):
        first = FakeTarget("first")
        indev = indev_of(first)
        indev.press((5, 5), now=0)

        indev.tick(LONG_PRESS_TIME - 0.01)
        indev.tick(LONG_PRESS_TIME + 0.01)
        indev.tick(LONG_PRESS_TIME + 0.02)
        indev.tick(LONG_PRESS_TIME + 0.01 + LONG_PRESS_REPEAT_TIME + 0.01)
        indev.release((5, 5))

        # the release after a long press is not a short click
        assert first.calls == ["press", "pressing", "long", "repeat", "release short=False"]

    def test_cancel_loses_the_press_and_forget_does_not_tell_the_object(self):
        first = FakeTarget("first")
        indev = indev_of(first)
        indev.press((5, 5), now=0)
        indev.cancel()
        indev.press((5, 5), now=1)
        indev.forget()

        assert first.calls == ["press", "pressing", "lost", "press", "pressing"]
        assert not indev.is_pressing


class TestRuntimeState(TestBase):
    def test_a_value_set_by_a_touch_is_shown_instead_of_the_draft(self):
        runtime = RuntimeState()
        draft = {"obj": "switch", "val": 0}

        runtime.set((1, 2), "val", 1, draft)

        assert runtime.effective((1, 2), draft)["val"] == 1
        assert runtime.get((1, 2), "val", draft) == 1
        # another object, and the draft itself, stay as they are
        assert runtime.effective((1, 3), draft) is draft
        assert draft["val"] == 0

    def test_the_draft_wins_when_it_changes_the_property_afterwards(self):
        runtime = RuntimeState()
        draft = {"obj": "slider", "val": 10}
        runtime.set((1, 2), "val", 70, draft)

        draft["val"] = 20

        assert runtime.effective((1, 2), draft)["val"] == 20
        assert runtime.is_empty

    def test_a_change_of_another_property_keeps_the_touched_value(self):
        runtime = RuntimeState()
        draft = {"obj": "slider", "val": 10, "min": 0}
        runtime.set((1, 2), "val", 70, draft)

        draft["min"] = 5

        assert runtime.effective((1, 2), draft)["val"] == 70

    def test_names_that_are_no_properties_stay(self):
        runtime = RuntimeState()
        draft = {"obj": "btnmatrix"}
        runtime.set((1, 2), "_checked", (1,), draft)

        draft["options"] = "A\nB"

        assert runtime.get((1, 2), "_checked", draft) == (1,)

    def test_clear_forgets_everything(self):
        runtime = RuntimeState()
        runtime.set((1, 2), "val", 1, {})
        runtime.pressed = (1, 2)
        runtime.closed.add((1, 3))

        runtime.clear()

        assert runtime.is_empty


class TestClickable(TestBase):
    def test_labels_images_lines_and_bars_ignore_touches_unless_they_say_click(self):
        for kind in ("label", "img", "line", "bar", "qrcode"):
            assert not is_clickable({"obj": kind})
            assert is_clickable({"obj": kind, "click": True})
            assert is_clickable({"obj": kind, "click": "1"})
        for kind in ("btn", "obj", "switch", "slider", "arc", "led", "msgbox"):
            assert is_clickable({"obj": kind})
        assert not is_clickable({"obj": "btn", "click": False})

    def test_hidden_and_disabled_objects_ignore_touches(self):
        assert not is_clickable({"obj": "btn", "hidden": True})
        assert not is_clickable({"obj": "btn", "hidden": "1"})
        assert not is_clickable({"obj": "btn", "enabled": False})
        assert is_clickable({"obj": "btn", "enabled": True, "hidden": 0})


class TestActions(TestBase):
    def test_the_old_actions_lead_to_a_page_on_release(self):
        assert action_commands("next", "up") == ["page next"]
        assert action_commands("PREV", "up") == ["page prev"]
        assert action_commands("back", "up") == ["page back"]
        assert action_commands("p3", "up") == ["page 3"]
        assert action_commands("next", "down") == []

    def test_a_json_action_has_commands_per_event(self):
        action = '{"down": "page 2", "up": ["page 5", "p1b2.val 1"], "long": "page back"}'

        assert action_commands(action, "down") == ["page 2"]
        assert action_commands(action, "up") == ["page 5", "p1b2.val 1"]
        assert action_commands(action, "long") == ["page back"]
        assert action_commands(action, "release") == []
        # the same as a JSON object in the jsonl
        assert action_commands({"up": "page 4"}, "up") == ["page 4"]

    def test_something_else_is_no_action(self):
        assert action_commands(None, "up") == []
        assert action_commands("", "up") == []
        assert action_commands("{broken", "up") == []
        assert action_commands("anything", "up") == []

    def test_page_commands_name_where_the_plate_goes(self):
        assert page_command("page next") == "next"
        assert page_command("page 7") == 7
        assert page_command("PAGE back") == "back"
        assert page_command("p1b2.val 1") is None
        assert page_command("page") is None
        assert page_command("page nowhere") is None


class TestGroups(TestBase):
    OBJECTS = [
        {"page": 1, "id": 1, "obj": "switch", "groupid": 3},
        {"page": 1, "id": 2, "obj": "slider", "groupid": 3, "min": 0, "max": 200},
        {"page": 2, "id": 1, "obj": "checkbox", "groupid": 3},
        {"page": 2, "id": 2, "obj": "btn", "groupid": 3, "toggle": True},
        {"page": 2, "id": 3, "obj": "btn", "groupid": 3},
        {"page": 2, "id": 4, "obj": "switch", "groupid": 4},
        {"page": 2, "id": 5, "obj": "label", "groupid": 3},
        {"page": 2, "id": 6, "obj": "led", "groupid": 3},
    ]

    def test_the_other_objects_of_the_group_follow_a_switch_on_every_page(self):
        values = group_values(self.OBJECTS, self.OBJECTS[0], power=True, value=1, minimum=0, maximum=1)

        # the slider goes to the end of its range, the toggles are on, the button that doesn't toggle and the other group don't follow
        assert values == {(1, 2): 200, (2, 1): 1, (2, 2): 1, (2, 6): 255}

    def test_a_group_member_that_is_off_goes_to_its_minimum(self):
        values = group_values(self.OBJECTS, self.OBJECTS[0], power=False, value=0, minimum=0, maximum=1)

        assert values == {(1, 2): 0, (2, 1): 0, (2, 2): 0, (2, 6): 0}

    def test_a_value_is_mapped_to_the_range_of_the_member(self):
        values = group_values(self.OBJECTS, self.OBJECTS[1], power=True, value=50, minimum=0, maximum=200)

        # a quarter of the way: the led is at a quarter, a toggle is on as soon as it is not at its minimum
        assert values == {(1, 1): 1, (2, 1): 1, (2, 2): 1, (2, 6): 63}

    def test_objects_without_a_group_or_without_a_range_have_no_followers(self):
        assert group_values(self.OBJECTS, {"obj": "switch", "groupid": 0}, True, 1, 0, 1) == {}
        assert group_values(self.OBJECTS, self.OBJECTS[0], True, 1, 5, 5) == {}
        assert value_range({"obj": "label"}) is None
        assert value_range({"obj": "dropdown"}) is None
        assert value_range({"obj": "btn"}) is None
        assert value_range({"obj": "btn", "toggle": 1}) == (0, 1)

    def test_a_tabview_follows_with_the_number_of_its_tabs(self):
        objects = [
            {"page": 1, "id": 1, "obj": "tabview"},
            {"page": 1, "id": 2, "obj": "tab", "parentid": 1},
            {"page": 1, "id": 3, "obj": "tab", "parentid": 1},
            {"page": 1, "id": 4, "obj": "tab", "parentid": 1},
        ]

        assert value_range(objects[0], objects) == (0, 2)


class TestTouchValues(TestBase):
    def test_c_division_rounds_towards_zero(self):
        assert c_div(7, 2) == 3
        assert c_div(-7, 2) == -3
        assert c_div(7, -2) == -3
        assert c_div(-7, -2) == 3

    def test_lv_map_is_limited_to_its_ranges(self):
        assert lv_map(5, 0, 10, 0, 100) == 50
        assert lv_map(-5, 0, 10, 0, 100) == 0
        assert lv_map(50, 0, 10, 0, 100) == 100
        assert lv_map(1, 0, 3, 0, 10) == 3

    def test_a_horizontal_slider_has_the_value_of_the_finger_on_its_track(self):
        # a track of 200 pixels with 6 of padding on both sides: the indicator is 188 pixels wide, from x = 6
        assert slider_value(6, 200, 6, 6, 0, 100, vertical=False) == 0
        assert slider_value(100, 200, 6, 6, 0, 100, vertical=False) == 50
        assert slider_value(194, 200, 6, 6, 0, 100, vertical=False) == 100
        # beyond the ends
        assert slider_value(-20, 200, 6, 6, 0, 100, vertical=False) == 0
        assert slider_value(500, 200, 6, 6, 0, 100, vertical=False) == 100

    def test_a_slider_with_a_range_that_does_not_start_at_zero(self):
        assert slider_value(100, 200, 6, 6, -50, 50, vertical=False) == 0
        assert slider_value(6, 200, 6, 6, 10, 20, vertical=False) == 10

    def test_a_vertical_slider_grows_from_its_bottom(self):
        # 100 pixels high, no padding: the bottom pixel is 99
        assert slider_value(99, 100, 0, 0, 0, 100, vertical=True) == 0
        assert slider_value(0, 100, 0, 0, 0, 100, vertical=True) == 99
        assert slider_value(50, 100, 0, 0, 0, 100, vertical=True) == 49

    def test_the_atan2_of_lvgl_counts_clockwise_from_the_second_argument(self):
        # the arc calls it with y and x swapped, which makes it count from 3 o'clock
        assert lvgl_atan2(0, 10) == 0
        assert lvgl_atan2(10, 0) == 90
        assert lvgl_atan2(0, -10) == 180
        assert lvgl_atan2(-10, 0) == 270
        assert abs(lvgl_atan2(10, 10) - 45) <= 1

    def test_the_last_angle_of_an_arc_follows_its_value_and_type(self):
        assert arc_last_angle(0, 0, 0, 100, 135, 45) == 135
        assert arc_last_angle(0, 100, 0, 100, 135, 45) == 405
        assert arc_last_angle(0, 50, 0, 100, 135, 45) == 270
        # symmetric: the halves of the scale each get the half of the way
        assert arc_last_angle(1, 75, 0, 100, 135, 45) == 337

    def _drag(self, drag, dx, dy, current=0, now=0.0, **overrides):
        arguments = dict(
            radius=100,
            indicator_width=15,
            background_start=135,
            background_end=45,
            rotation=0,
            minimum=0,
            maximum=100,
            current_value=current,
            last_angle=arc_last_angle(0, current, 0, 100, 135, 45),
            now=now,
        )
        arguments.update(overrides)
        return arc_value(drag, dx, dy, **arguments)

    def test_an_arc_does_not_turn_while_the_finger_is_in_its_middle(self):
        drag = ArcDrag()

        assert self._drag(drag, 10, 10) is None
        assert not drag.dragging

    def test_an_arc_turns_to_the_finger_on_its_ring(self):
        drag = ArcDrag()
        drag.dragging = True

        # straight up (270 degrees) is the middle of the scale from 135 to 405, a long time after the last change
        value = self._drag(drag, 0, -90, current=40, now=10.0)

        assert value == 50

    def test_an_arc_turns_only_as_fast_as_the_change_rate_allows(self):
        drag = ArcDrag()
        self._drag(drag, 90, 0, current=0, now=0.0)

        # straight up is 135 degrees away from the start: in 0.1 s it turns 54 degrees at most (540 degrees per second)
        value = self._drag(drag, 0, -90, current=0, now=0.1)

        assert value == round(54 / 270 * 100)

    def test_an_arc_does_not_jump_over_the_gap_of_its_scale(self):
        drag = ArcDrag()
        # at the end of the scale, then the finger crosses the gap (down at 90 degrees is between 45 and 135)
        self._drag(drag, 90, 0, current=100, now=0.0, last_angle=405)
        drag.min_close = False

        value = self._drag(drag, -5, 90, current=100, now=10.0, last_angle=405)

        assert value == 100
