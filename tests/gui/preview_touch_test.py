"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""

import math

import pytest

from openhasp_config_manager.gui.domain.roller_scroll import settled_option
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


def drag(view, item, *points):
    """The finger touches at the first point (if it is not down yet), then is at each point for one read of the plate (20 ms)."""
    for point in points:
        view.finger(point, 0.0)
        item._scroll.tick()


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


def center(item, rect):
    point = item.mapToScene(rect.center())
    return point.x(), point.y()


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


def QtCore_point(x, y):
    from PyQt6 import QtCore

    return QtCore.QPointF(x, y)


TABVIEW = {"page": 1, "id": 11, "obj": "tabview", "x": 0, "y": 0, "w": 300, "h": 200, "val": 0}
TABS = [{"page": 1, "id": 12 + n, "obj": "tab", "parentid": 11, "text": f"T{n}"} for n in range(3)]


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
        assert item.indicator_position == 0
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


def swipe(view, item, *points):
    """The finger touches at the first point (if it is not down yet), then is at each point for one read of the plate (20 ms)."""
    for point in points:
        view.finger(point, 0.0)
        item.read_swipe()


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
