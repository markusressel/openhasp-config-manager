
import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.gui.page_layout_editor.helpers import DOT_INCLUDE, DOT_JSONL, EDITOR_JSONL, _object, _sent_objects


class TestIncludedObjects(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {
            "common/parts/dot.jsonl": DOT_JSONL,
            "devices/test_device/editor.jsonl": EDITOR_JSONL + DOT_INCLUDE,
        }

    def _select(self, editor, obj_id: int):
        editor.set_edit_mode(True)
        obj = _object(editor, obj_id)
        editor.page_preview_widget.select_object(obj)
        return obj

    def test_included_objects_are_shown_but_cant_be_dragged(self, editor):
        # GIVEN
        editor.set_edit_mode(True)
        editor.page_preview_widget.refresh_movable()

        # THEN
        items = {item.obj_data.get("id"): item for item in editor.page_preview_widget.editable_items()}
        assert items[20].obj_data["x"] == 200 and items[21].obj_data["text"] == "21"
        assert items[20].movable is False
        assert items[1].movable is True

    def test_the_live_preview_sends_the_included_objects_too(self, editor, plate):
        # WHEN
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))

        # THEN
        assert {(9, 1), (9, 20), (9, 21)} <= set(_sent_objects(plate))

    def test_the_actions_leave_included_objects_alone_and_explain_why(self, editor, monkeypatch):
        from PyQt6.QtWidgets import QApplication, QMessageBox

        # GIVEN
        editor.resize(900, 700)
        editor.show()
        failures = []
        editor.status.failed.connect(lambda *args: failures.append(args))
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        QApplication.clipboard().setText("nothing")
        obj = self._select(editor, 20)

        # WHEN
        editor.object_actions.nudge_selected(1, 0)
        editor.object_actions.use_pixel_positions()
        editor.object_actions.duplicate_selected()
        editor.object_actions.copy_selected()
        editor.object_actions.remove_selected()

        # THEN
        assert [failure[0] for failure in failures] == [
            "Moving p9b20",
            "Using pixels for p9b20",
            "Duplicating p9b20",
            "Copying p9b20",
            "Removing p9b20",
        ]
        assert failures[0][1] == "an !include puts it into the file: change it in the part, or the vars of the !include"
        assert editor.page_preview_widget._message.text().startswith(
            "p9b20 can't be changed here:\nIt is included from common/parts/dot.jsonl:1"
        )
        assert QApplication.clipboard().text() == "nothing"
        assert any(other is obj for other in editor.page_objects)
        assert editor.session.is_dirty is False
        assert editor.session.undo_description is None

    def test_the_properties_are_read_only_and_lead_to_the_part_and_the_directive(self, editor, tmp_path):
        from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

        # GIVEN
        editor.property_editor.set_session(editor.session)
        requested = []
        editor.openSourceRequested.connect(lambda path, line: requested.append((path, line)))

        # WHEN
        self._select(editor, 21)
        buttons = {button.text(): button for button in editor.property_editor.findChildren(QPushButton)}
        buttons["Open the part"].click()
        buttons["Go to the !include"].click()

        # THEN
        root = tmp_path / "cfg"
        assert requested == [(root / "common/parts/dot.jsonl", 1), (root / "devices/test_device/editor.jsonl", 4)]
        assert "Remove Object" not in buttons and "Duplicate Object" not in buttons
        # only the vars and for of the !include can be changed
        assert {field.objectName(): field.text() for field in editor.property_editor.findChildren(QLineEdit)} == {
            "vars.prefix": "",
            "for.id": "[20, 21]",
        }
        texts = [label.text() for label in editor.property_editor.findChildren(QLabel)]
        assert {"p9b21", "label", "common/parts/dot.jsonl:1", "included", "This instance: 21"} <= set(texts)
        assert "The !include at devices/test_device/editor.jsonl:4" in texts
        assert "shared" not in texts
        assert "210" in texts

    def _field(self, editor, name: str):
        from PyQt6.QtWidgets import QLineEdit

        return editor.property_editor.findChild(QLineEdit, name)

    def _error(self, field) -> str:
        from PyQt6.QtWidgets import QLabel

        [label] = [label for label in field.parentWidget().findChildren(QLabel) if label.property("role") == "error"]
        return label.text()

    def test_a_var_edit_renders_the_instances_again_without_making_the_panel_again(self, editor):
        from PyQt6.QtWidgets import QLabel

        # GIVEN
        obj = self._select(editor, 21)
        field = self._field(editor, "vars.prefix")

        # WHEN
        field.setText("#")

        # THEN
        assert (_object(editor, 20)["text"], obj["text"]) == ("#20", "#21")
        assert self._field(editor, "vars.prefix") is field
        assert "#21" in [label.text() for label in editor.property_editor.findChildren(QLabel)]
        assert editor.session.is_dirty is True
        assert editor.action_undo.text() == "Undo Change vars.prefix of the !include"

        # WHEN: typing on is the same step
        field.setText("#:")
        editor.undo()

        # THEN
        assert obj["text"] == "21"

    def test_a_for_edit_adds_instances_and_keeps_the_selection(self, editor):
        # GIVEN
        obj = self._select(editor, 21)

        # WHEN
        self._field(editor, "for.id").setText("[20, 21, 22]")

        # THEN
        assert _object(editor, 22)["x"] == 220
        assert [item.obj_data for item in editor.page_preview_widget.selected_items()] == [obj]
        assert self._field(editor, "for.id").text() == "[20, 21, 22]"

    def test_an_invalid_value_is_shown_and_not_applied(self, editor):
        # GIVEN
        self._select(editor, 21)
        field = self._field(editor, "for.id")

        # WHEN: not JSON yet
        field.setText("[20,")

        # THEN
        assert self._error(field) == "Write a JSON list of values, e.g. [1, 2, 3], or use a template."

        # WHEN: an id that another object has
        field.setText("[1, 21]")

        # THEN
        assert self._error(field).startswith("p9b1 of common/parts/dot.jsonl:1 (id=1) is also the id of")
        assert editor.session.is_dirty is False
        assert [obj.get("id") for obj in editor.page_objects if obj.get("page") == 9] == [1, 2, 20, 21]

    def test_a_template_value(self, editor):
        from PyQt6.QtWidgets import QToolButton

        # GIVEN
        self._select(editor, 21)
        toggle = self._field(editor, "for.id").parentWidget().findChild(QToolButton)

        # WHEN
        toggle.setChecked(True)
        self._field(editor, "for.id").setText("{{ range(21, 24) }}")

        # THEN
        assert {21, 22, 23} <= {obj.get("id") for obj in editor.page_objects}
        assert editor.session.source_of(_object(editor, 21))["text"] == "{{ prefix }}{{ id }}"

    def test_the_live_preview_deletes_the_removed_instances(self, editor, plate):
        # GIVEN
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        self._select(editor, 20)
        plate.clear()

        # WHEN
        self._field(editor, "for.id").setText("[20]")

        # THEN
        wait_until(lambda: plate.calls)
        assert plate.calls == [("delete_object_id", 9, 21)]


class TestNestedVars(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {
            "common/parts/bar.jsonl": '{"page": 9, "id": "{{ bar.id }}", "obj": "label", "text": "{{ bar.text }}"}\n',
            "devices/test_device/editor.jsonl": EDITOR_JSONL
            + '{"!include": "common/parts/bar.jsonl", "vars": {"bar": {"id": 30, "text": "2:35"}}}\n',
        }

    def test_a_var_that_is_a_mapping_has_a_field_for_each_value(self, editor):
        from PyQt6.QtWidgets import QLineEdit

        # GIVEN
        editor.set_edit_mode(True)
        obj = _object(editor, 30)
        editor.page_preview_widget.select_object(obj)
        fields = {field.objectName(): field for field in editor.property_editor.findChildren(QLineEdit)}
        assert {name: field.text() for name, field in fields.items()} == {"vars.bar.id": "30", "vars.bar.text": "2:35"}

        # WHEN: the text stays a text, also when it looks like a number
        fields["vars.bar.text"].setText("12")

        # THEN
        assert obj["text"] == "12"
        assert editor.session.directive_of(obj)["vars"] == {"bar": {"id": 30, "text": "12"}}

        # WHEN: the id is JSON
        fields["vars.bar.id"].setText("31")

        # THEN
        assert editor.session.directive_of(_object(editor, 31))["vars"] == {"bar": {"id": 31, "text": "12"}}


class TestSharedInclude(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {"common/parts/dot.jsonl": DOT_JSONL, "common/editor.jsonl": EDITOR_JSONL + DOT_INCLUDE}

    @pytest.fixture
    def boot_cmd(self):
        return "run L:/common_editor.jsonl\n"

    def test_a_directive_in_the_common_folder_is_marked_as_shared(self, editor):
        from PyQt6.QtWidgets import QLabel

        # WHEN
        editor.set_edit_mode(True)
        editor.page_preview_widget.select_object(_object(editor, 20))

        # THEN
        texts = [label.text() for label in editor.property_editor.findChildren(QLabel)]
        assert "shared" in texts
        assert "The !include is in a shared file: saving a change changes the pages of every device that loads it." in texts
