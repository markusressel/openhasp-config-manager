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
