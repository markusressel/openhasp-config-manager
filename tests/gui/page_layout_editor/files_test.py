
import orjson

from tests import TestBase
from tests.gui.page_layout_editor.helpers import _key, _object


class TestFiles(TestBase):
    def test_new_objects_go_to_the_chosen_file(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)

        # WHEN
        editor.object_actions.add(OpenHASPWidgetType.LABEL)

        # THEN
        added = editor.working_objects[home][-1]
        assert (added["page"], added["obj"]) == (9, "label")
        assert editor.target_component == home

    def test_a_new_tab_goes_into_the_tabview_of_the_page(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)
        editor.object_actions.add(OpenHASPWidgetType.TABVIEW)
        tabview = editor.working_objects[home][-1]

        # WHEN
        editor.object_actions.add(OpenHASPWidgetType.TAB)

        # THEN
        assert editor.working_objects[home][-1]["parentid"] == tabview["id"]

    def test_a_tab_needs_a_tabview_on_the_page(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)
        count = len(editor.working_objects[home])

        # WHEN
        editor.object_actions.add(OpenHASPWidgetType.TAB)

        # THEN
        assert len(editor.working_objects[home]) == count

    def test_removing_an_object_rebuilds_the_properties_once(self, editor, monkeypatch):
        # GIVEN
        from PyQt6.QtWidgets import QMessageBox

        editor.set_edit_mode(True)
        item = editor.page_preview_widget.editable_items()[0]
        item.setSelected(True)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args: QMessageBox.StandardButton.Yes))
        rebuilds = []
        original = editor.property_editor._create_content
        monkeypatch.setattr(editor.property_editor, "_create_content", lambda: rebuilds.append(1) or original())

        # WHEN
        editor.object_actions.remove_selected()

        # THEN
        assert len(rebuilds) == 1
        assert len(editor.page_preview_widget.editable_items()) == 1

    def test_removing_several_selected_objects(self, editor, monkeypatch):
        # GIVEN
        from PyQt6.QtWidgets import QMessageBox

        editor.set_edit_mode(True)
        for item in editor.page_preview_widget.editable_items():
            item.setSelected(True)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args: QMessageBox.StandardButton.Yes))

        # WHEN (this crashed: clearing the scene reported the selection of objects that were removed already)
        editor.object_actions.remove_selected()

        # THEN
        assert editor.page_preview_widget.editable_items() == []
        assert editor.property_editor._editable_widgets == []

    def test_the_problems_never_name_removed_objects(self, editor, monkeypatch):
        # GIVEN: objects with problems (outside of the screen), and a listener that looks them up like SourceEditorSync
        from PyQt6.QtWidgets import QMessageBox

        editor.set_edit_mode(True)
        for item in editor.page_preview_widget.editable_items():
            editor.session.set_source_value(item.obj_data, "x", 1000)
        assert editor.problems
        looked_up = []
        editor.stateChanged.connect(lambda: looked_up.extend(editor.session.line_of(p.obj) for p in editor.problems))
        for item in editor.page_preview_widget.editable_items():
            item.setSelected(True)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args: QMessageBox.StandardButton.Yes))

        # WHEN (this crashed: rebuilding the page reported the selection while the problems still named the removed objects)
        editor.object_actions.remove_selected()

        # THEN
        assert editor.problems == []

    def test_removing_an_object_while_its_file_is_highlighted(self, editor, monkeypatch):
        # GIVEN
        from PyQt6.QtWidgets import QMessageBox

        editor.set_edit_mode(True)
        editor.highlight_component(_key(editor, "editor.jsonl"))
        editor.page_preview_widget.editable_items()[0].setSelected(True)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args: QMessageBox.StandardButton.Yes))

        # WHEN
        editor.object_actions.remove_selected()

        # THEN
        assert len(editor.page_preview_widget.editable_items()) == 1

    def test_the_chosen_file_is_remembered_for_the_next_start(self, editor, settings):
        # GIVEN
        from openhasp_config_manager.gui.domain.file_tree import config_root_of
        from openhasp_config_manager.gui.qt.operations import OperationStatus
        from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget

        root = config_root_of(editor.session.device.path)

        def start():
            widget = PageLayoutEditorWidget(status=OperationStatus(), ui_session=UiSessionStore(root, settings))
            widget.set_data(session=editor.session, device_pages_data=editor.device_pages_data, page=9)
            return widget

        home = _key(editor, "page.jsonl")

        # WHEN
        start().set_target_component(home)

        # THEN
        assert start().target_component == home

    def test_without_a_choice_new_objects_go_to_the_file_of_the_page(self, editor):
        assert editor.target_component == _key(editor, "editor.jsonl")

    def test_file_state_has_the_pages_of_each_file(self, editor):
        # WHEN
        pages, page, target = editor.file_state()

        # THEN
        assert pages[_key(editor, "editor.jsonl")] == {1, 9}
        assert page == 9
        assert target == _key(editor, "editor.jsonl")

    def test_highlighting_a_file_dims_the_objects_of_the_other_files(self, editor):
        # GIVEN
        editor.set_page_index(1)

        # WHEN
        editor.highlight_component(_key(editor, "editor.jsonl"))

        # THEN
        opacity = {item.obj_id: item.opacity() for item in editor.page_preview_widget.editable_items()}
        assert opacity[50] == 1.0
        assert opacity[1] < 1.0

    def test_selecting_an_object_of_another_file_ends_the_highlight(self, editor):
        # GIVEN
        editor.set_page_index(1)
        editor.set_edit_mode(True)
        editor.highlight_component(_key(editor, "editor.jsonl"))
        revealed = []
        editor.selectedObjectComponentChanged.connect(revealed.append)
        home_label = next(obj for obj in editor.page_objects if obj.get("id") == 1)

        # WHEN
        editor.page_preview_widget.select_object(home_label)

        # THEN
        assert revealed == [_key(editor, "page.jsonl")]
        assert all(item.opacity() == 1.0 for item in editor.page_preview_widget.editable_items() if item.obj_id in (1, 50))


class TestHighlightComponent(TestBase):
    def _dimmed_ids(self, editor):
        return [
            orjson.loads(selection.cursor.block().text())["id"]
            for selection in editor.jsonl_preview.extraSelections()
            if selection.format.foreground().color().alpha() < 255
        ]

    def test_the_jsonl_dims_the_objects_of_other_files(self, editor):
        # GIVEN: the objects of page 9 are all in editor.jsonl
        ids = {obj["id"] for obj in editor.page_objects}

        # WHEN
        editor.highlight_component(_key(editor, "page.jsonl"))
        other_file = set(self._dimmed_ids(editor))
        editor.highlight_component(_key(editor, "editor.jsonl"))
        same_file = set(self._dimmed_ids(editor))
        editor.highlight_component(None)

        # THEN
        assert other_file == ids
        assert same_file == set()
        assert editor.jsonl_preview.extraSelections() == []

    def test_selecting_an_object_dims_the_lines_of_other_files_but_not_the_preview(self, editor):
        # GIVEN: an object of another file on page 9
        other = editor.session.add_object(
            _key(editor, "page.jsonl"), {"page": 9, "id": 60, "obj": "label", "text": "other", "x": 0, "y": 0}
        )
        editor.set_edit_mode(True)
        editor.set_page_index(9)
        preview = editor.page_preview_widget
        own = _object(editor, 1)

        # WHEN
        preview.select_object(own)
        dimmed_while_selected = set(self._dimmed_ids(editor))
        dimmed_items = [item.obj_data["id"] for item in preview.editable_items() if item.opacity() < 1]
        preview.select_object(other)
        dimmed_for_other = set(self._dimmed_ids(editor))
        preview.scene().clearSelection()

        # THEN
        assert dimmed_while_selected == {60}
        assert dimmed_items == []
        assert dimmed_for_other == {obj["id"] for obj in editor.page_objects} - {60}
        assert self._dimmed_ids(editor) == []
