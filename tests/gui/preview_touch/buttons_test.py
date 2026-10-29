"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""


import pytest

from tests import TestBase
from tests.gui.preview_touch.helpers import BUTTON, flush, lift, preview, tap, widget


def color_at(view, x, y) -> str:
    from PyQt6 import QtCore, QtGui

    image = QtGui.QImage(480, 320, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor("black"))
    painter = QtGui.QPainter(image)
    view.scene().render(painter, QtCore.QRectF(0, 0, 480, 320), QtCore.QRectF(0, 0, 480, 320))
    painter.end()
    return image.pixelColor(x, y).name().upper()


MATRIX = {
    "page": 1,
    "id": 9,
    "obj": "btnmatrix",
    "x": 10,
    "y": 10,
    "w": 300,
    "h": 60,
    "options": ["A", "B", "C"],
    "toggle": True,
}


@pytest.mark.usefixtures("qapp")
class TestPreviewTouch(TestBase):
    def test_a_button_looks_pressed_while_the_finger_is_on_it(self):
        view = preview(BUTTON)

        view._indev.press((20, 20), 0.0)
        assert widget(view, 1).is_pressed
        view._indev.release((20, 20))

        assert not widget(view, 1).is_pressed

    def test_a_button_loses_the_press_when_the_finger_leaves_it(self):
        view = preview({**BUTTON, "action": "next"})

        view._indev.press((20, 20), 0.0)
        view._indev.press((300, 200), 0.1)
        view._indev.release((300, 200))

        assert not widget(view, 1).is_pressed
        assert view.commands == []

    def test_releasing_a_button_runs_its_action(self):
        view = preview({**BUTTON, "action": "p3"})

        tap(view, 20, 20)

        assert view.commands == ["page 3"]

    def test_a_json_action_runs_on_the_event(self):
        view = preview({**BUTTON, "action": '{"down": "page 2", "up": "page 5"}'})

        view._indev.press((20, 20), 0.0)
        flush()
        assert view.commands == ["page 2"]
        view._indev.release((20, 20))
        flush()

        assert view.commands == ["page 2", "page 5"]

    def test_an_action_sets_properties_of_other_objects(self):
        label = {"page": 1, "id": 2, "obj": "label", "x": 10, "y": 100, "w": 100, "h": 30, "text": "Off"}
        switch = {"page": 2, "id": 3, "obj": "switch", "x": 10, "y": 10, "w": 80, "h": 40}
        action = '{"up": ["p1b2.text=On air", "p2b3.val 1", "p1b9.val 1", "p1b2.val"]}'
        view = preview({**BUTTON, "action": action}, label)
        view.set_group_objects(lambda: [BUTTON, label, switch])

        tap(view, 20, 20)

        assert widget(view, 2).data["text"] == "On air"
        assert view.runtime.get((2, 3), "val", switch) == 1
        # an object that doesn't exist changes nothing, and a command without a value only asks
        assert "val" not in widget(view, 2).data

    def test_a_toggle_button_changes_its_state_and_runs_no_action(self):
        view = preview({**BUTTON, "toggle": True, "action": "next"})

        tap(view, 20, 20)
        assert widget(view, 1).is_toggled
        tap(view, 20, 20)

        assert not widget(view, 1).is_toggled
        assert view.commands == []

    def test_the_draft_is_not_changed_by_touching(self):
        draft = {**BUTTON, "toggle": True}
        view = preview(draft)

        tap(view, 20, 20)

        assert "val" not in draft and draft["toggle"] is True

    def test_a_label_is_not_touched_unless_it_is_clickable(self):
        label = {"page": 1, "id": 2, "obj": "label", "x": 10, "y": 100, "w": 100, "h": 30, "text": "Hi", "action": "next"}
        view = preview(label)

        tap(view, 20, 110)
        assert view.commands == []
        view.set_objects([{**label, "click": True}])
        tap(view, 20, 110)

        assert view.commands == ["page next"]

    def test_a_switch_toggles_on_release_wherever_the_finger_is(self):
        view = preview({"page": 1, "id": 3, "obj": "switch", "x": 10, "y": 10, "w": 80, "h": 40, "action": "next"})

        view._indev.press((20, 20), 0.0)
        view._indev.release((300, 250))

        assert widget(view, 3).is_toggled
        assert view.commands == []

    def test_the_knob_of_a_switch_moves_to_the_other_end_in_its_anim_time(self):
        view = preview({"page": 1, "id": 3, "obj": "switch", "x": 10, "y": 10, "w": 80, "h": 40, "anim_time": 500})
        item = widget(view, 3)
        off = item._knob_rect(item.obj_rect).x()

        tap(view, 20, 20)

        # the value is on at once, the knob starts at the off end
        assert item.is_toggled
        assert item._anim.duration() == 500
        assert item._knob_rect(item.obj_rect).x() == off
        item.finish_animation()
        assert item.position == 1.0
        assert item._knob_rect(item.obj_rect).x() > off

    def test_a_switch_with_anim_time_0_does_not_animate(self):
        view = preview({"page": 1, "id": 3, "obj": "switch", "x": 10, "y": 10, "w": 80, "h": 40, "anim_time": 0})

        tap(view, 20, 20)

        assert widget(view, 3)._anim is None
        assert widget(view, 3).position == 1.0

    def test_a_checkbox_toggles(self):
        view = preview({"page": 1, "id": 4, "obj": "checkbox", "x": 10, "y": 10, "w": 150, "h": 40, "text": "On"})

        tap(view, 20, 20)

        assert widget(view, 4).is_toggled

    def test_a_slider_follows_the_finger_and_keeps_it_when_the_finger_leaves(self):
        view = preview(
            {"page": 1, "id": 5, "obj": "slider", "x": 10, "y": 10, "w": 200, "h": 20, "min": 0, "max": 100, "val": 0}
        )

        view._indev.press((110, 20), 0.0)
        view._indev.press((110, 200), 0.1)
        view._indev.release((110, 200))

        assert 45 <= widget(view, 5).data["val"] <= 55

    def test_a_range_slider_moves_the_knob_nearer_to_the_finger_up_to_the_other_one(self):
        slider = {
            "page": 1,
            "id": 5,
            "obj": "slider",
            "x": 10,
            "y": 10,
            "w": 200,
            "h": 20,
            "type": 2,
            "start_value": 20,
            "val": 80,
        }
        view = preview(slider)
        item = widget(view, 5)

        # WHEN: the finger is nearer to the knob at 20
        view._indev.press((70, 20), 0.0)
        view._indev.press((110, 20), 0.1)

        # THEN: the track starts at 16 and is 188 wide
        assert (item.data["start_value"], item.data["val"]) == (50, 80)

        # WHEN: past the other knob
        view._indev.press((200, 20), 0.2)
        view._indev.release((200, 20))

        # THEN
        assert (item.data["start_value"], item.data["val"]) == (80, 80)

        # WHEN: right of the knob at `val`
        view._indev.press((205, 20), 0.0)
        view._indev.press((150, 20), 0.1)
        view._indev.release((150, 20))

        # THEN
        assert (item.data["start_value"], item.data["val"]) == (80, 80)

        # WHEN: the knobs are on top of each other: the finger left of them takes the start
        view._indev.press((30, 20), 0.0)
        view._indev.release((30, 20))

        assert (item.data["start_value"], item.data["val"]) == (7, 80)

    def test_a_slider_value_does_not_go_below_its_start_value(self):
        slider = {"page": 1, "id": 5, "obj": "slider", "x": 10, "y": 10, "w": 200, "h": 20, "start_value": 40, "val": 80}
        view = preview(slider)

        view._indev.press((30, 20), 0.0)
        view._indev.release((30, 20))

        assert widget(view, 5).data["val"] == 40

    def test_a_group_follows_a_switch_on_the_page(self):
        switch = {"page": 1, "id": 3, "obj": "switch", "x": 10, "y": 10, "w": 80, "h": 40, "groupid": 2}
        slider = {
            "page": 1,
            "id": 5,
            "obj": "slider",
            "x": 10,
            "y": 100,
            "w": 200,
            "h": 20,
            "min": 0,
            "max": 100,
            "val": 0,
            "groupid": 2,
        }
        view = preview(switch, slider)
        view.set_group_objects(lambda: [switch, slider])

        tap(view, 20, 20)

        assert widget(view, 5).data["val"] == 100

    def test_the_draft_wins_when_it_changes_a_touched_value(self):
        slider = {"page": 1, "id": 5, "obj": "slider", "x": 10, "y": 10, "w": 200, "h": 20, "min": 0, "max": 100, "val": 0}
        view = preview(slider)
        tap(view, 110, 20)

        slider["val"] = 10
        view.set_objects([slider])

        assert widget(view, 5).data["val"] == 10

    def test_reset_shows_the_draft_again(self):
        view = preview({**BUTTON, "toggle": True})
        tap(view, 20, 20)

        view.reset_interactions()

        assert not widget(view, 1).is_toggled

    def test_edit_mode_does_not_react_to_the_mouse_as_a_finger(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PreviewMode

        view = preview({**BUTTON, "toggle": True, "action": "next"}, mode=PreviewMode.Edit)

        assert not view._indev.is_pressing
        view.set_mode(PreviewMode.Interact)
        tap(view, 20, 20)
        view.set_mode(PreviewMode.Edit)

        assert not widget(view, 1).is_toggled


@pytest.mark.usefixtures("qapp")
class TestPreviewLook(TestBase):
    def test_a_pressed_button_has_the_pressed_colors_of_the_theme(self):
        view = preview({**BUTTON, "bg_grad_dir": 0})
        normal = color_at(view, 60, 20)

        view.finger((60, 20), 0.0)
        pressed = color_at(view, 60, 20)
        view._indev.release((60, 20))

        assert pressed != normal
        assert color_at(view, 60, 20) == normal


@pytest.mark.usefixtures("qapp")
class TestPreviewButtonMatrix(TestBase):
    def test_the_button_under_the_finger_is_pressed_and_follows_it(self):
        view = preview(MATRIX)
        item = widget(view, 9)
        rects = [rect for rect, _ in item.button_rects()]
        first, second = ((rect.center().x() + 10, rect.center().y() + 10) for rect in rects[:2])

        view.finger(first, 0.0)
        assert item.runtime.pressed_part == 0
        view.finger(second, 0.1)
        assert item.runtime.pressed_part == 1
        view._indev.release(second)

        assert item.runtime.pressed_part is None

    def test_a_released_button_of_a_toggling_matrix_is_checked_and_released_again_unchecked(self):
        view = preview(MATRIX)
        item = widget(view, 9)
        rects = [rect for rect, _ in item.button_rects()]
        points = [(rect.center().x() + 10, rect.center().y() + 10) for rect in rects]

        lift(view, *points[0])
        lift(view, *points[2])
        assert item.checked_buttons() == (0, 2)
        lift(view, *points[0])

        assert item.checked_buttons() == (2,)

    def test_with_one_check_only_the_last_button_is_checked_and_it_is_the_value(self):
        view = preview({**MATRIX, "one_check": True, "val": 0})
        item = widget(view, 9)
        rects = [rect for rect, _ in item.button_rects()]
        points = [(rect.center().x() + 10, rect.center().y() + 10) for rect in rects]
        assert item.checked_buttons() == (0,)
        # `val` before `one_check` is not taken by the plate
        assert preview({**MATRIX, "val": 0, "one_check": True}).editable_items()[0].checked_buttons() == ()

        lift(view, *points[1])

        assert item.checked_buttons() == (1,)
        assert item.data["val"] == 1

    def test_a_matrix_without_toggle_checks_nothing(self):
        view = preview({**MATRIX, "toggle": False})
        item = widget(view, 9)
        rect = item.button_rects()[0][0]

        lift(view, rect.center().x() + 10, rect.center().y() + 10)

        assert item.checked_buttons() == ()
