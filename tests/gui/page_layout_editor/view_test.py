import math

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.gui.page_layout_editor.helpers import _key, _object


class TestNavigationButtons(TestBase):
    def test_a_click_on_prev_changes_the_page_after_the_click_is_handled(self, editor):
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtTest import QTest

        # GIVEN
        editor.resize(900, 700)
        editor.show()
        editor.set_edit_mode(False)
        key = _key(editor, "editor.jsonl")
        button = editor.session.add_object(
            key, {"page": 9, "id": 50, "obj": "btn", "text": "prev", "x": 300, "y": 200, "w": 80, "h": 40, "action": "prev"}
        )
        editor.set_page_index(9)
        preview = editor.page_preview_widget
        [item] = [item for item in preview.editable_items() if item.obj_data is button]

        # WHEN
        QTest.mouseClick(preview.viewport(), Qt.MouseButton.LeftButton, pos=preview.mapFromScene(QPointF(320, 220)))

        # THEN the button outlives the click: changing the page clears the scene, which deleted it while it handled the
        # click (a crash)
        assert item.scene() is preview.scene()
        wait_until(lambda: editor.current_index != 9)


class TestPageSelection(TestBase):
    def test_every_page_and_the_global_page_can_be_chosen(self, editor):
        # THEN: also pages without objects
        combo = editor.page_combo
        assert [combo.itemData(i) for i in range(combo.count())] == list(range(0, 13))
        assert combo.itemText(0) == "Global (page 0)"
        assert combo.itemText(7) == "Page 7"

        # WHEN
        editor._go_to_page(0)

        # THEN: only what is on all pages
        assert editor.current_index == 0
        assert combo.currentData() == 0
        assert all(obj.get("page") == 0 for obj in editor.page_objects)

    def test_interactive_buttons_follow_the_settings_of_the_pages(self, editor):
        # GIVEN: the buttons of page 9 lead to 4 and not to the page the toolbar would go to
        key = _key(editor, "editor.jsonl")
        editor.session.add_object(key, {"page": 9, "id": 0, "next": 4})
        editor.set_page_index(9)

        # WHEN: a touch on a button with the action next runs its command
        editor._PageLayoutEditorWidget__on_preview_command("page next")

        # THEN
        assert editor.current_index == 4

        # WHEN: the toolbar ignores the settings
        editor.set_page_index(9)
        editor._on_next_page_clicked()
        assert editor.current_index == 10

    def test_the_arrows_go_through_the_pages_of_the_dropdown(self, editor):
        visited = [editor.current_index]
        editor._go_to_page(11)
        for _ in range(3):
            editor._on_next_page_clicked()
            visited.append(editor.current_index)
        assert visited[1:] == [12, 0, 1]
        editor._on_previous_page_clicked()
        assert editor.current_index == 0
        editor._on_previous_page_clicked()
        assert editor.current_index == 12


class TestScreenBrightness(TestBase):
    def _lightness(self, editor) -> int:
        from PyQt6.QtWidgets import QApplication

        QApplication.processEvents()
        image = editor.page_preview_widget.viewport().grab().toImage()
        # the middle of the view is on the plate
        return image.pixelColor(image.width() // 2, image.height() // 2).lightness()

    def test_the_slider_darkens_the_preview_and_off_darkens_it_most(self, editor):
        # GIVEN: a white object over the whole plate
        editor.resize(900, 700)
        editor.show()
        component = editor.session.components[0].key
        editor.session.add_object(
            component, {"page": 9, "id": 99, "obj": "btn", "x": 0, "y": 0, "w": 2000, "h": 2000, "bg_color": "#FFFFFF"}
        )
        editor.set_page_index(9)
        editor.page_preview_widget.fit_to_view()
        controls = editor.device_controls

        # WHEN
        full = self._lightness(editor)
        controls._brightness_slider.setValue(20)
        dim = self._lightness(editor)
        controls.screenChanged.emit(20, False)
        off = self._lightness(editor)
        controls.screenChanged.emit(100, True)
        back = self._lightness(editor)

        # THEN
        assert full > dim > off
        assert back == full


class TestOutsideTheScreen(TestBase):
    def _pixel(self, editor, scene_x: float, scene_y: float):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QApplication

        QApplication.processEvents()
        view = editor.page_preview_widget
        point = view.mapFromScene(QPointF(scene_x, scene_y))
        return view.viewport().grab().toImage().pixelColor(point.x(), point.y())

    def test_the_part_of_an_object_outside_the_screen_is_striped_red(self, editor):
        # GIVEN: an object that sticks out of the right edge of the plate
        editor.resize(900, 700)
        editor.show()
        plate = editor.page_preview_widget.scene().sceneRect()
        component = editor.session.components[0].key
        editor.session.add_object(
            component,
            {
                "page": 9,
                "id": 99,
                "obj": "btn",
                "x": int(plate.width()) - 50,
                "y": 0,
                "w": 100,
                "h": 100,
                "bg_color": "#FFFFFF",
                "bg_grad_dir": 0,
                "border_width": 0,
            },
        )
        editor.set_page_index(9)
        editor.page_preview_widget.fit_to_view()

        # WHEN
        outside = self._pixel(editor, plate.width() + 8, 50)
        inside = self._pixel(editor, plate.width() - 8, 50)

        # THEN: the stripes are red-ish, where the object is on the screen it is plain white
        assert outside.red() > outside.blue() + 20
        assert (inside.red(), inside.green(), inside.blue()) == (255, 255, 255)


class TestProblemsPanel(TestBase):
    def test_it_lists_what_is_outside_of_the_screen_and_selects_it_on_click(self, editor):
        # GIVEN
        editor.set_edit_mode(True)
        editor.show()
        assert editor.problems_panel.isHidden()
        obj = _object(editor, 1)

        # WHEN
        editor.session.set_source_value(obj, "x", -20)
        editor.set_page_index(9)

        # THEN
        panel = editor.problems_panel
        assert not panel.isHidden()
        assert panel._header.text() == "1 warning"
        panel._header.setChecked(True)
        panel._list.setCurrentRow(0)
        assert [item.obj_data for item in editor.page_preview_widget.selected_items()] == [obj]

        # and it goes away when the object is back
        editor.session.set_source_value(obj, "x", 0)
        editor.set_page_index(9)
        assert panel.isHidden()


def test_the_jsonl_shows_objects_that_share_an_id_when_only_one_has_a_position(qapp):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget

    preview = PageJsonlPreviewWidget()

    preview.set_objects([{"page": 1, "id": 2, "y": 5}, {"page": 1, "id": 2}])

    assert len(preview.toPlainText().splitlines()) == 2


class TestZoomSlider(TestBase):
    def test_the_slider_zooms_the_preview_and_follows_other_zoom_changes(self, editor):
        # GIVEN
        editor.resize(900, 700)
        editor.show()
        preview = editor.page_preview_widget
        slider = editor.zoom_slider

        # WHEN
        slider.setValue(100)
        maximum = preview.zoom()
        slider.setValue(0)
        minimum = preview.zoom()
        preview.zoom_in()
        stepped = slider.value()
        preview.fit_to_view()

        # THEN
        assert maximum == pytest.approx(8.0)
        assert minimum == pytest.approx(0.25)
        assert stepped > 0
        assert 0 < slider.value() < 100
        assert slider.value() == round(100 * math.log(preview.zoom() / 0.25) / math.log(32))


class TestPageIndicator(TestBase):
    def _click(self, indicator, x: float):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        position = QPointF(x, 3)
        indicator.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                position,
                indicator.mapToGlobal(position),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

    def test_it_has_a_segment_per_page_and_shows_the_current_one(self, editor):
        indicator = editor.page_indicator
        editor._go_to_page(5)
        assert indicator._pages == list(range(0, 13))
        assert indicator._current == 5
        assert [page for page in indicator._pages if indicator._counts.get(page)] == [1, 9]
        assert "empty" in indicator._description(2)
        assert "objects" in indicator._description(9)

    def test_a_click_on_a_segment_or_the_gap_after_it_goes_to_its_page(self, editor):
        indicator = editor.page_indicator
        editor._go_to_page(5)
        self._click(indicator, indicator._segment(3).left() + 2)
        assert editor.current_index == 3
        editor._go_to_page(5)
        self._click(indicator, indicator._segment(3).right() + 1)
        assert editor.current_index == 3

    def test_it_is_painted(self, editor):
        assert not editor.page_indicator.grab().isNull()


class TestInteractMode(TestBase):
    """What touching the objects of the preview changed lives next to the draft: never in it, and not in edit mode."""

    def _touch(self, editor):
        editor.page_preview_widget.runtime.set((9, 2), "val", 1, _object(editor, 2))
        editor.page_preview_widget.runtime.open_dropdown = (9, 5)

    def test_touching_does_not_change_the_draft(self, editor):
        self._touch(editor)

        assert "val" not in _object(editor, 2)
        assert not editor.session.is_dirty

    def test_going_to_another_page_keeps_what_was_touched(self, editor):
        self._touch(editor)

        editor._go_to_page(1)
        editor._go_to_page(9)

        assert not editor.page_preview_widget.runtime.is_empty

    def test_edit_mode_shows_the_draft_and_forgets_the_touches(self, editor):
        self._touch(editor)

        editor.set_edit_mode(True)

        assert editor.page_preview_widget.runtime.is_empty

    def test_reset_forgets_the_touches_and_is_only_there_in_interact_mode(self, editor):
        self._touch(editor)

        editor.action_reset_interactions.trigger()
        assert editor.page_preview_widget.runtime.is_empty
        assert editor.action_reset_interactions.isVisible()
        editor.set_edit_mode(True)

        assert not editor.action_reset_interactions.isVisible()
        editor.set_edit_mode(False)
        assert editor.action_reset_interactions.isVisible()

    def test_a_new_value_of_the_draft_wins_over_the_touched_one(self, editor):
        self._touch(editor)

        editor.session.set_source_value(_object(editor, 2), "val", 0)

        assert editor.page_preview_widget.runtime.get((9, 2), "val", _object(editor, 2)) == 0
