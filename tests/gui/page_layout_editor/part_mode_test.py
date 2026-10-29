
import pytest

from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from tests import TestBase
from tests.gui.page_layout_editor.helpers import DOT_INCLUDE, DOT_JSONL, EDITOR_JSONL, _object


PIN_INCLUDE = '{"!include": "common/parts/pin.jsonl", "for": {"id": [40, 41]}}\n'


# a part with pixel positions, two instances
PIN_JSONL = '{"page": 9, "id": "{{ id }}", "obj": "label", "x": 5, "y": 7, "text": "{{ id }}"}\n'


class TestPartMode(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {
            "common/parts/dot.jsonl": DOT_JSONL,
            "common/parts/pin.jsonl": PIN_JSONL,
            "devices/test_device/editor.jsonl": EDITOR_JSONL + DOT_INCLUDE + PIN_INCLUDE,
        }

    def _select(self, editor, obj_id: int):
        editor.set_edit_mode(True)
        obj = _object(editor, obj_id)
        editor.page_preview_widget.select_object(obj)
        return obj

    def _items(self, editor):
        return {item.obj_data.get("id"): item for item in editor.page_preview_widget.editable_items()}

    def _edit_part_of(self, editor, obj_id: int):
        """Click "Edit the part" for an object, and show the part like the part tab the window opens for it."""
        from PyQt6.QtWidgets import QPushButton

        self._select(editor, obj_id)
        [button] = [button for button in editor.property_editor.findChildren(QPushButton) if button.text() == "Edit the part"]
        requested = []
        editor.editPartRequested.connect(lambda part, instance: requested.append((part, instance)))
        button.click()
        [(_part, instance)] = requested
        self._focus(editor, instance)

    def _focus(self, editor, instance):
        editor.set_data(editor.session, editor.device_pages_data, focus=PartFocus(editor.session, instance))
        editor.set_edit_mode(True)

    def test_the_panel_asks_for_part_mode_where_only_the_instance_can_be_changed(self, editor, tmp_path):
        # WHEN
        self._edit_part_of(editor, 21)

        # THEN
        assert editor.part_mode.part == (tmp_path / "cfg/common/parts/dot.jsonl").resolve()
        assert not editor.part_bar.isHidden()
        assert editor.part_bar.title.full_text == "dot.jsonl"
        assert editor.part_bar.title.toolTip().startswith("Editing the part common/parts/dot.jsonl, instance at")
        assert editor.part_bar.instances.currentIndex() == 1
        assert editor.part_bar.instances.currentText() == "editor.jsonl:4 (id=21)"
        items = self._items(editor)
        assert (items[21].editable, items[20].editable, items[1].editable, items[40].editable) == (True, False, False, False)
        assert editor.target_component == str(editor.part_mode.part)

    def test_only_the_objects_of_the_instance_are_shown_zoomed_to_fit_them_unless_the_page_is_shown(self, editor):
        # GIVEN
        preview = editor.page_preview_widget
        preview.resize(800, 600)
        preview.fit_to_view()
        plate_zoom = preview.zoom()

        # WHEN
        self._edit_part_of(editor, 21)

        # THEN: the page is rendered, but only the instance is shown, zoomed in
        assert {obj.get("id") for obj in editor.page_objects} == {1, 2, 20, 21, 40, 41}
        assert [item.obj_data.get("id") for item in preview.editable_items() if item.isVisible()] == [21]
        focused_zoom = preview.zoom()
        assert focused_zoom > plate_zoom
        assert preview.fits_to_view

        # WHEN
        editor.part_bar.show_page.click()

        # THEN: the page around it, dimmed, the whole plate in view
        assert editor.shows_page
        assert all(item.isVisible() for item in preview.editable_items())
        dimmed = [obj.get("id") for obj in editor.page_objects if preview._is_dimmed(obj)]
        assert dimmed == [1, 2, 20, 40, 41]
        assert not preview.is_focused and preview.zoom() < focused_zoom

    def test_an_edit_in_the_instance_changes_every_instance_and_done_asks_to_close_the_tab(self, editor):
        # GIVEN
        self._edit_part_of(editor, 21)
        done = []
        editor.partDone.connect(lambda: done.append(True))

        # WHEN
        editor.editing.set_source_value(_object(editor, 21), "text", "-{{ id }}")

        # THEN
        assert (_object(editor, 20)["text"], _object(editor, 21)["text"]) == ("-20", "-21")
        assert editor.session.is_dirty is True

        # WHEN
        editor.part_bar.done.click()

        # THEN
        assert done == [True]

    def test_another_instance_can_be_chosen(self, editor):
        # GIVEN
        self._edit_part_of(editor, 21)
        focus = editor.part_focus

        # WHEN
        editor.part_bar.instances.setCurrentIndex(0)

        # THEN: in the same part mode, which the tab owns
        assert editor.part_focus is focus
        items = self._items(editor)
        assert (items[20].editable, items[21].editable) == (True, False)
        assert [item.obj_data.get("id") for item in editor.page_preview_widget.editable_items() if item.isVisible()] == [20]

    def test_nudging_moves_the_objects_of_every_instance(self, editor):
        # GIVEN
        self._edit_part_of(editor, 41)
        assert self._items(editor)[41].movable is True

        # WHEN
        editor.page_preview_widget.select_object(_object(editor, 41))
        editor.object_actions.nudge_selected(3, 0)

        # THEN
        assert (_object(editor, 40)["x"], _object(editor, 41)["x"]) == (8, 8)

    def test_using_pixels_asks_first_because_every_instance_gets_them(self, editor, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        # GIVEN
        self._edit_part_of(editor, 21)
        editor.page_preview_widget.select_object(_object(editor, 21))
        answers = [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes]
        questions = []

        def question(_parent, title, text, *args):
            questions.append(title)
            return answers.pop(0)

        monkeypatch.setattr(QMessageBox, "question", question)

        # WHEN: cancelled
        editor.object_actions.use_pixel_positions()

        # THEN
        assert questions == ["Use pixels in the part"]
        assert editor.session.is_dirty is False

        # WHEN
        editor.object_actions.use_pixel_positions()

        # THEN: the pixels of this instance, in every instance
        assert editor.session.source_of(_object(editor, 21))["x"] == 210
        assert _object(editor, 20)["x"] == 210

    def test_copying_is_refused(self, editor):
        from PyQt6.QtWidgets import QApplication

        # GIVEN
        failures = []
        editor.status.failed.connect(lambda *args: failures.append(args))
        QApplication.clipboard().setText("nothing")
        self._edit_part_of(editor, 21)
        editor.page_preview_widget.select_object(_object(editor, 21))

        # WHEN
        editor.object_actions.copy_selected()

        # THEN
        assert failures == [
            ("Copying p9b21", "the objects of a part need the variables of their instance: duplicate them instead")
        ]
        assert QApplication.clipboard().text() == "nothing"

    def test_the_objects_outside_of_the_instance_cant_be_selected(self, editor):
        # GIVEN
        self._edit_part_of(editor, 21)
        editor.page_preview_widget.select_object(_object(editor, 21))

        # WHEN: the selection can't hold an object of another instance
        editor.page_preview_widget.select_object(_object(editor, 1))

        # THEN
        assert editor.page_preview_widget.selected_items() == []

    def test_part_mode_shows_the_page_of_its_instance(self, editor, tmp_path):
        # GIVEN
        editor.set_page_index(1)
        [first, _second] = editor.session.part_instances(tmp_path / "cfg/common/parts/pin.jsonl")

        # WHEN
        self._focus(editor, first)

        # THEN
        assert editor.current_index == 9
        items = self._items(editor)
        assert (items[40].editable, items[41].editable) == (True, False)
        assert editor.part_bar.info.isHidden() is False

    def test_pasting_into_the_part(self, editor):
        from PyQt6.QtWidgets import QApplication

        # GIVEN: a plain object copied
        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, 1))
        editor.object_actions.copy_selected()
        self._edit_part_of(editor, 21)

        # WHEN
        editor.object_actions.paste()

        # THEN: in every instance, selected in the one that is shown
        assert "label" in QApplication.clipboard().text()
        [pasted] = [item.obj_data for item in editor.page_preview_widget.selected_items()]
        assert editor.session.source_of(pasted)["id"] == "{{ id + 1 }}"
        assert editor.session.instance_of(pasted) == editor.part_mode
        assert (pasted["id"], _object(editor, 21)["id"]) == (22, 21)
        assert editor.action_undo.text() == "Undo Paste 1 object into the part"

    def test_a_shared_part_says_which_devices_saving_changes(self, editor):
        # WHEN
        self._edit_part_of(editor, 21)

        # THEN
        assert editor.part_bar.info.toolTip() == (
            "A shared part: saving it changes every device that includes it (1 file of 1 device: test_device). "
            "Only the instances of test_device are shown."
        )
