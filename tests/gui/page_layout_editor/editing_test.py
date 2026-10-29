import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.gui.page_layout_editor.helpers import _object


class TestCopyPaste(TestBase):
    def _copy(self, editor, obj_id: int):
        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, obj_id))
        editor.action_copy.trigger()

    def test_copy_puts_the_sources_on_the_clipboard(self, editor):
        from PyQt6.QtWidgets import QApplication

        # WHEN
        self._copy(editor, 1)

        # THEN
        assert QApplication.clipboard().text() == '{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}\n'

    def test_repeated_pastes_next_to_the_original_cascade(self, editor, monkeypatch):
        # GIVEN
        monkeypatch.setattr(editor.page_preview_widget, "cursor_plate_position", lambda: None)
        self._copy(editor, 1)

        # WHEN
        editor.action_paste.trigger()
        editor.action_paste.trigger()

        # THEN
        pasted = [obj for obj in editor.page_objects if obj.get("id") in (3, 4)]
        assert [(obj["x"], obj["text"]) for obj in pasted] == [(20, "A"), (30, "A")]
        assert [item.obj_id for item in editor.page_preview_widget.selected_items()] == [4]
        assert editor.session.is_dirty

    def test_paste_goes_where_the_mouse_is(self, editor, monkeypatch):
        # GIVEN
        monkeypatch.setattr(editor.page_preview_widget, "cursor_plate_position", lambda: (200, 100))
        self._copy(editor, 1)

        # WHEN
        editor.set_page_index(1)
        editor.action_paste.trigger()

        # THEN
        pasted = editor.working_objects[editor.target_component][-1]
        assert (pasted["page"], pasted["x"], pasted["y"]) == (1, 200, 100)

    def test_paste_of_other_text_reports_it(self, editor):
        from PyQt6.QtWidgets import QApplication

        # GIVEN
        failures = []
        editor.status.failed.connect(lambda *args: failures.append(args))
        QApplication.clipboard().setText("hello")

        # WHEN
        editor.action_paste.trigger()

        # THEN
        assert failures == [("Pasting", "the clipboard holds no openHASP objects (JSONL)")]
        assert editor.session.is_dirty is False


class TestLockedPosition(TestBase):
    def _lock(self, editor, obj_id: int):
        editor.set_edit_mode(True)
        obj = _object(editor, obj_id)
        editor.session.set_source_value(obj, "x", "10%")
        editor.page_preview_widget.refresh_movable()
        self._item(editor, obj).refresh()
        return obj

    def _item(self, editor, obj):
        return next(item for item in editor.page_preview_widget.editable_items() if item.obj_data is obj)

    def test_dragging_a_locked_object_reports_it_once_and_shows_it_is_not_allowed(self, editor):
        from PyQt6 import QtCore
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication

        # GIVEN
        editor.resize(900, 700)
        editor.show()
        obj = self._lock(editor, 2)
        failures = []
        editor.status.failed.connect(lambda *args: failures.append(args))
        preview = editor.page_preview_widget
        viewport = preview.viewport()
        start = preview.mapFromScene(QPointF(obj["x"] + 5, obj.get("y", 0) + 5))

        # WHEN
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 4):
            point = QPointF(start + QtCore.QPoint(20 * step, 0))
            QApplication.sendEvent(
                viewport,
                QMouseEvent(
                    QtCore.QEvent.Type.MouseMove,
                    point,
                    QPointF(viewport.mapToGlobal(point)),
                    Qt.MouseButton.NoButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )
        cursor = viewport.cursor().shape()
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + QtCore.QPoint(60, 0))

        # THEN
        assert len(failures) == 1
        assert failures[0][0] == "Moving p9b2"
        assert cursor == Qt.CursorShape.ForbiddenCursor
        message = preview._message
        assert message.isVisible()
        assert message.text() == (
            "p9b2 can't be moved:\nx is a percentage: 10%\n"
            "To move it, use pixels for x/y in the properties: this replaces the template or percentage."
        )
        assert viewport.rect().contains(message.geometry())
        assert viewport.cursor().shape() != Qt.CursorShape.ForbiddenCursor
        assert editor.session.source_of(obj)["x"] == "10%"

    def test_nudging_a_locked_object_explains_it_until_the_next_click(self, editor):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        # GIVEN
        editor.resize(900, 700)
        editor.show()
        obj = self._lock(editor, 2)
        editor.page_preview_widget.select_object(obj)
        message = editor.page_preview_widget._message

        # WHEN
        editor.object_actions.nudge_selected(1, 0)
        shown = message.isVisible()
        QTest.mouseClick(editor.page_preview_widget.viewport(), Qt.MouseButton.LeftButton)

        # THEN
        assert shown
        assert message.isVisible() is False

    def test_use_pixel_positions_makes_the_selected_objects_movable(self, editor):
        # GIVEN
        obj = self._lock(editor, 2)
        x = obj["x"]
        editor.page_preview_widget.select_object(obj)
        assert self._item(editor, obj).movable is False

        # WHEN
        editor.property_editor.usePixelPositionClicked.emit()

        # THEN
        assert editor.session.source_of(obj)["x"] == x
        assert self._item(editor, obj).movable is True

    def test_the_properties_offer_to_use_pixels_only_for_a_locked_position(self, editor):
        from PyQt6.QtWidgets import QPushButton

        def offered() -> bool:
            return any(button.text() == "Use pixels for x/y" for button in editor.property_editor.findChildren(QPushButton))

        # GIVEN
        editor.property_editor.set_session(editor.session)
        obj = self._lock(editor, 2)

        # WHEN
        editor.page_preview_widget.select_object(_object(editor, 1))
        unlocked = offered()
        editor.page_preview_widget.select_object(obj)

        # THEN
        assert unlocked is False
        assert offered() is True


class TestObjectOnTab(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {
            "devices/test_device/editor.jsonl": (
                '{"page": 9, "id": 1, "obj": "tabview", "x": 20, "y": 20, "w": 400, "h": 280}\n'
                '{"page": 9, "id": 2, "obj": "tab", "parentid": 1, "text": "One"}\n'
                '{"page": 9, "id": 3, "obj": "btn", "x": 40, "y": 40, "w": 100, "h": 50, "parentid": 2, "text": "On tab"}\n'
            )
        }

    def test_dragging_an_object_on_a_tab_keeps_its_position_relative_to_the_tab(self, editor):
        from PyQt6 import QtCore
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtTest import QTest

        # GIVEN
        editor.resize(900, 700)
        editor.show()
        editor.set_edit_mode(True)
        editor.page_preview_widget.set_snap_enabled(False)
        preview = editor.page_preview_widget
        viewport = preview.viewport()
        # the button is at the content of the tab, under the buttons of the tabview
        start = preview.mapFromScene(QPointF(20 + 40 + 10, 20 + 62 + 40 + 10))

        # WHEN
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
        end = start + QtCore.QPoint(40, 0)
        QTest.mouseMove(viewport, start + QtCore.QPoint(20, 0))
        QTest.mouseMove(viewport, end)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)

        # THEN: it was selected and moved, not the tabview
        assert [item.obj_id for item in preview.selected_items()] == [3]
        moved = preview.mapToScene(end).x() - preview.mapToScene(start).x()
        assert abs(editor.session.source_of(_object(editor, 3))["x"] - (40 + moved)) < 1
        assert editor.session.source_of(_object(editor, 1))["x"] == 20


class TestPropertyDocs(TestBase):
    def _label(self, editor, key):
        from PyQt6.QtWidgets import QLabel

        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, 1))
        return next(label for label in editor.property_editor.findChildren(QLabel) if label.text() == f"{key}:")

    def test_the_name_of_a_property_explains_it(self, editor):
        # GIVEN the panel, which is in a dock of the main window (here a window of its own)
        panel = editor.property_editor
        panel.resize(400, 800)
        panel.show()
        hover = panel.hover

        # WHEN
        hover.show_for(self._label(editor, "text"))

        # THEN on the window, not in the narrow panel
        assert hover.card.isVisible()
        assert hover.card.parentWidget() is panel.window()
        assert hover.card._name.text() == "text"

    def test_a_property_that_is_not_in_the_file_says_so(self, editor):
        # GIVEN a property that the file doesn't have (e.g. a default of the theme)
        from PyQt6.QtWidgets import QLabel

        self._label(editor, "text")
        panel = editor.property_editor
        container = panel._create_property_label("bg_color", panel._editable_widgets[0].obj_data)
        label = next(label for label in container.findChildren(QLabel) if label.text() == "bg_color:")

        # WHEN
        content = editor.property_editor.hover._contents[label]()

        # THEN
        assert [message for _, message in content.issues] == [
            "Not in the file: a default of the theme or computed. Changing it writes it to the file."
        ]
        assert content.help.name == "bg_color"

    def test_the_card_goes_away_when_the_panel_is_made_again(self, editor):
        # GIVEN
        panel = editor.property_editor
        panel.resize(400, 800)
        panel.show()
        hover = panel.hover
        hover._label = self._label(editor, "text")
        hover.show_for(hover._label)

        # WHEN
        editor.property_editor.refresh()

        # THEN
        assert not hover.card.isVisible()


class TestUndo(TestBase):
    def _select(self, editor, obj_id: int):
        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, obj_id))

    def _selected_ids(self, editor):
        return [item.obj_data.get("id") for item in editor.page_preview_widget.selected_items()]

    def test_nothing_to_undo_at_first(self, editor):
        assert not editor.action_undo.isEnabled()
        assert not editor.action_redo.isEnabled()
        assert editor.action_undo.text() == "Undo"

    def test_nudging_again_and_again_is_one_step(self, editor):
        # GIVEN
        self._select(editor, 1)
        label = _object(editor, 1)

        # WHEN
        for _ in range(3):
            editor.object_actions.nudge_selected(1, 0)

        # THEN
        assert label["x"] == 13
        assert editor.action_undo.isEnabled()
        assert editor.action_undo.text() == "Undo Move p9b1"

        # WHEN
        editor.undo()

        # THEN
        assert _object(editor, 1)["x"] == 10
        assert editor.session.is_dirty is False
        assert not editor.action_undo.isEnabled()
        assert editor.action_redo.text() == "Redo Move p9b1"
        assert self._selected_ids(editor) == [1]

        # WHEN
        editor.redo()

        # THEN
        assert _object(editor, 1)["x"] == 13
        assert editor.session.is_dirty is True

    def test_undoing_a_removal_brings_the_objects_back_selected(self, editor, monkeypatch):
        # GIVEN
        from PyQt6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args: QMessageBox.StandardButton.Yes))
        self._select(editor, 1)
        _item = next(item for item in editor.page_preview_widget.editable_items() if item.obj_data.get("id") == 2)
        _item.setSelected(True)
        editor.object_actions.remove_selected()
        assert len(editor.page_preview_widget.editable_items()) == 0
        assert editor.action_undo.text() == "Undo Remove 2 objects"

        # WHEN
        editor.undo()

        # THEN
        assert sorted(self._selected_ids(editor)) == [1, 2]
        assert editor.session.is_dirty is False

    def test_undo_shows_the_page_of_the_change(self, editor):
        # GIVEN
        editor.set_page_index(1)
        other = next(obj for obj in editor.page_objects if obj.get("id") == 50)
        editor.session.set_source_value(other, "text", "F")
        editor.set_page_index(9)

        # WHEN
        editor.undo()

        # THEN
        assert editor.current_index == 1
        assert next(obj for obj in editor.page_objects if obj.get("id") == 50)["text"] == "E"

    def test_typing_into_a_property_is_one_step_until_another_object_is_selected(self, editor):
        # GIVEN
        self._select(editor, 1)
        properties = editor.property_editor

        # WHEN typing
        for text in ["Ab", "Abc"]:
            properties._on_property_edited("text", text, properties._editable_widgets[0])
        # and again after another object was selected
        self._select(editor, 2)
        self._select(editor, 1)
        properties._on_property_edited("text", "Abcd", properties._editable_widgets[0])

        # THEN
        assert editor.action_undo.text() == "Undo Change text of p9b1"
        editor.undo()
        assert _object(editor, 1)["text"] == "Abc"
        editor.undo()
        assert _object(editor, 1)["text"] == "A"
        assert not editor.action_undo.isEnabled()

    def test_resetting_all_properties_is_one_step(self, editor):
        # GIVEN
        self._select(editor, 1)
        properties = editor.property_editor
        properties._on_property_edited("text", "B", properties._editable_widgets[0])
        properties._on_property_edited("x", 50, properties._editable_widgets[0])

        # WHEN
        properties._reset_all_to_snapshot()

        # THEN
        label = _object(editor, 1)
        assert (label["text"], label["x"]) == ("A", 10)
        assert editor.session.is_dirty is False
        assert editor.action_undo.text() == "Undo Reset p9b1"
        editor.undo()
        assert (_object(editor, 1)["text"], _object(editor, 1)["x"]) == ("B", 50)

    def test_live_preview_follows_an_undo(self, editor, plate):
        # GIVEN
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        self._select(editor, 1)
        editor.object_actions.nudge_selected(5, 0)
        editor.object_actions.nudge_selected(5, 0)
        wait_until(lambda: plate.calls[-1] == ("jsonl", {"page": 9, "id": 1, "x": 20}))
        plate.clear()

        # WHEN
        editor.undo()

        # THEN the move set y too, which the plate can't unset: it gets the page again
        wait_until(lambda: ("jsonl", {"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}) in plate.calls)
        assert plate.calls[0] == ("clear_page", 9)


class TestWidgetPicker(TestBase):
    def test_the_list_of_object_types_scrolls_instead_of_growing_the_preview(self, editor):
        from openhasp_config_manager.gui.domain.draft.page_objects import WIDGET_TYPES

        # THEN: all types are offered, but they don't make the editor taller than a small window
        assert len(WIDGET_TYPES) > 20
        assert editor.widget_picker.minimumSizeHint().height() < 300
        assert editor.minimumSizeHint().height() < 600

    def test_the_buttons_fit_next_to_the_scrollbar(self, qapp):
        from PyQt6.QtWidgets import QScrollArea

        from openhasp_config_manager.gui.qt.widgets.pagelayout.widget_picker import OpenHASPWidgetPicker

        picker = OpenHASPWidgetPicker()
        picker.resize(picker.width(), 300)
        picker.show()
        qapp.processEvents()

        # THEN the list scrolls, and its buttons are not cut off by the scrollbar
        scroll_area = picker.findChild(QScrollArea)
        assert scroll_area.verticalScrollBar().isVisible()
        assert scroll_area.viewport().width() >= scroll_area.widget().sizeHint().width()
        picker.close()


class TestPropertyEditor(TestBase):
    def _template_field(self, editor):
        from PyQt6.QtWidgets import QLineEdit

        return next(
            field for field in editor.property_editor.findChildren(QLineEdit) if field.placeholderText() == "{{ variable }}"
        )

    def test_a_template_that_is_not_valid_yet_survives_a_rebuild_of_the_panel(self, editor):
        # GIVEN
        editor.set_edit_mode(True)
        editor.property_editor.set_session(editor.session)
        obj = _object(editor, 1)
        editor.page_preview_widget.select_object(obj)
        widget = editor.property_editor._editable_widgets[0]
        editor.property_editor._set_template_mode(widget, "text", True)
        self._template_field(editor).setText("{{ nope")

        # WHEN: e.g. the object was moved
        editor.property_editor.refresh()

        # THEN
        assert self._template_field(editor).text() == "{{ nope"
        assert editor.session.is_template(obj, "text") is False

    def test_a_template_starts_with_its_braces_and_the_cursor_between_them(self, editor):
        # GIVEN
        editor.set_edit_mode(True)
        editor.property_editor.set_session(editor.session)
        obj = _object(editor, 1)
        editor.page_preview_widget.select_object(obj)
        widget = editor.property_editor._editable_widgets[0]

        # WHEN
        editor.property_editor._set_template_mode(widget, "text", True)

        # THEN nothing is checked or written yet
        field = self._template_field(editor)
        assert (field.text(), field.cursorPosition()) == ("{{  }}", 3)
        assert editor.session.is_template(obj, "text") is False
        assert obj["text"] == "A"

    def test_typing_into_the_braces_makes_a_template(self, editor):
        # GIVEN
        editor.set_edit_mode(True)
        editor.property_editor.set_session(editor.session)
        obj = _object(editor, 1)
        editor.page_preview_widget.select_object(obj)
        editor.property_editor._set_template_mode(editor.property_editor._editable_widgets[0], "text", True)
        field = self._template_field(editor)

        # WHEN
        field.insert("1 + 1")

        # THEN
        assert field.text() == "{{ 1 + 1 }}"
        assert editor.session.is_template(obj, "text") is True

    def test_typing_does_not_rebuild_the_panel_but_a_move_does(self, editor, monkeypatch):
        # GIVEN
        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, 1))
        properties = editor.property_editor
        rebuilds = []
        original = properties._create_content
        monkeypatch.setattr(properties, "_create_content", lambda: rebuilds.append(1) or original())

        # WHEN typing
        properties._on_property_edited("text", "Ab", properties._editable_widgets[0])

        # THEN the field keeps its focus and cursor, the preview shows the text
        assert rebuilds == []
        assert _object(editor, 1)["text"] == "Ab"

        # WHEN the object is moved in the preview
        editor.object_actions.nudge_selected(1, 0)

        # THEN the panel shows the new x
        assert rebuilds == [1]
