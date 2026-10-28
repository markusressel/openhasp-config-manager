"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""

import pytest

from tests import TestBase


def preview(*objects: dict, mode=None):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode

    view = PagePreviewWidget()
    view.set_mode(mode or PreviewMode.Interact)
    view.set_objects(list(objects))
    view.commands = []
    view.commandRequested.connect(view.commands.append)
    return view


def widget(view, object_id: int):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

    return next(item for item in view.scene().items() if isinstance(item, EditableWidget) and item.data.get("id") == object_id)


def flush():
    """Commands are run from the event loop, not inside of the touch."""
    from PyQt6 import QtCore

    QtCore.QCoreApplication.processEvents()


def tap(view, x, y, now=0.0):
    view._indev.press((x, y), now)
    view._indev.release((x, y))
    flush()


BUTTON = {"page": 1, "id": 1, "obj": "btn", "x": 10, "y": 10, "w": 100, "h": 50, "text": "Go"}


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


DROPDOWN = {"page": 1, "id": 6, "obj": "dropdown", "x": 10, "y": 10, "w": 200, "h": 40, "options": "One\nTwo\nThree", "val": 1}


def lift(view, x, y):
    view.finger((x, y), 0.0)
    view._indev.release((x, y))
    flush()


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

    def test_the_list_opens_above_without_room_below_and_is_hit_there(self):
        view = preview({**DROPDOWN, "y": 280, "h": 30})
        lift(view, 20, 290)

        opened = widget(view, 6).open_layout()

        assert opened.y + opened.h == 280
        assert widget(view, 6).hit(widget(view, 6).mapFromScene(20, 200))


ROLLER = {"page": 1, "id": 8, "obj": "roller", "x": 10, "y": 10, "w": 120, "rows": 3, "options": "A\nB\nC\nD\nE", "val": 1}


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
        # the rows start where they were, one row off, and animate to the new option
        assert item._offset == pytest.approx(row)
        item.finish_animation()
        assert item._offset == 0
        assert draft["val"] == 1

    def test_dragging_moves_the_rows_and_letting_go_selects_the_nearest_option(self):
        view = preview(ROLLER)
        item = widget(view, 8)
        row = self.row_height(view)

        view.finger((20, 60), 0.0)
        view.finger((20, 60 - 10 - row * 1.6), 0.1)
        assert item._offset == pytest.approx(-row * 1.6)
        # the finger can leave the roller while it drags
        view.finger((400, 60 - 10 - row * 1.6), 0.2)
        view._indev.release((400, 60 - 10 - row * 1.6))

        assert item.data["val"] == 3
        item.finish_animation()

    def test_a_roller_stops_at_its_last_option(self):
        view = preview(ROLLER)
        view.finger((20, 100), 0.0)
        view.finger((20, 100 - 10 - 1000), 0.1)
        view._indev.release((20, 100 - 1010))

        assert widget(view, 8).data["val"] == 4
        widget(view, 8).finish_animation()

    def test_a_roller_in_infinite_mode_wraps_around(self):
        view = preview({**ROLLER, "mode": 1, "val": 4})
        row = self.row_height(view)
        view.finger((20, 100), 0.0)
        view.finger((20, 100 - 10 - row), 0.1)
        view._indev.release((20, 100 - 10 - row))

        assert widget(view, 8).data["val"] == 0
        widget(view, 8).finish_animation()

    def test_the_selected_band_looks_pressed_while_touched(self):
        view = preview(ROLLER)

        view.finger((20, 60), 0.0)

        assert widget(view, 8).is_pressed
        view._indev.release((20, 60))
        widget(view, 8).finish_animation()
