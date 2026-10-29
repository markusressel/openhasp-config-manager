import json
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.variables.usages import Usage  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.source.usages_popup import show_usages_popup  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.helpers import EDITOR_JSONL, create_editor_cfg_root, gui_state, wait_until, x_of_label  # noqa: E402


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return create_editor_cfg_root(tmp_path)


@pytest.fixture
def window(create_window):
    window = create_window()
    wait_until(lambda: window.devices)
    window.on_device_selected("test_device")
    wait_until(lambda: window.session is not None and window.session.is_loaded)
    window.page_layout_editor_widget.set_page_index(9)
    window.page_layout_editor_widget.set_edit_mode(True)
    return window


@pytest.fixture
def editor_file(cfg_root) -> Path:
    return (cfg_root / "devices" / "test_device" / "editor.jsonl").resolve()


@pytest.fixture
def unused_file(cfg_root) -> Path:
    # written before the window loads the device
    path = cfg_root / "devices" / "test_device" / "vars.yaml"
    path.write_text("unused_one: 1\nunused_two: 2\n")
    return path.resolve()


@pytest.fixture
def used_variables(cfg_root) -> Path:
    # `shared` is used by two files, `single` by one, `nobody` by none. Written before the window loads the device
    device = cfg_root / "devices" / "test_device"
    path = device / "vars.yaml"
    path.write_text("shared: 1\nsingle: 2\nnobody: 3\n")
    editor = device / "editor.jsonl"
    editor.write_text(
        editor.read_text()
        + '{"page": 9, "id": 9, "obj": "label", "text": "{{ shared }} {{ single }}"}\n'
        + '{"page": 9, "id": 10, "obj": "label", "text": "{{ shared }}"}\n'
    )
    return path.resolve()


class TestNavigationHistory(TestBase):
    def _click(self, editor, button):
        QTest.mouseClick(editor.viewport(), button, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))

    def test_back_and_forward_buttons_follow_the_jumps(self, used_variables, window, editor_file):
        # GIVEN: the cursor is in vars.yaml, from where the user jumps to the one usage of `single`
        window.file_tree_widget.openRequested.emit(used_variables)
        window.source_editor.current_editor.go_to(2, 3)
        window.source_editor._show_usages(used_variables, "single", QPoint(0, 0))
        assert window.source_editor.current_file == editor_file

        # WHEN: back
        self._click(window.source_editor.current_editor, Qt.MouseButton.BackButton)

        # THEN: the place the jump came from
        assert window.source_editor.current_file == used_variables
        assert window.source_editor.location.line == 2
        assert window.source_editor.location.column == 4

        # WHEN: forward
        self._click(window.source_editor.current_editor, Qt.MouseButton.ForwardButton)

        # THEN
        assert window.source_editor.current_file == editor_file
        assert window.source_editor.location.line == 3

    def test_nothing_happens_without_history(self, used_variables, window):
        window.file_tree_widget.openRequested.emit(used_variables)
        window.source_editor.go_back()
        window.source_editor.go_forward()
        assert window.source_editor.current_file == used_variables

    def test_previews_and_restored_tabs_are_no_jumps(self, used_variables, window, editor_file):
        window.file_tree_widget.openRequested.emit(used_variables)
        window.source_editor.open_file(editor_file, 1, preview=True)
        window.source_editor.open_file(used_variables, focus=False)
        window.source_editor.go_back()
        assert window.source_editor.current_file == used_variables


class TestUsagesOfVariables(TestBase):
    def test_ctrl_click_on_a_key_without_usages_says_so(self, used_variables, window):
        # GIVEN
        window.file_tree_widget.openRequested.emit(used_variables)

        # WHEN
        window.source_editor._show_usages(used_variables, "nobody", QPoint(0, 0))

        # THEN
        assert window.source_editor._status.text() == "nobody is not used"

    def test_a_single_usage_is_opened(self, used_variables, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(used_variables)

        # WHEN
        window.source_editor._show_usages(used_variables, "single", QPoint(0, 0))

        # THEN
        assert window.source_editor.current_file == editor_file
        assert window.source_editor.current_editor.cursor_line_column[0] == 3

    def test_several_usages_are_listed_to_choose_from(self, used_variables, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(used_variables)
        editor = window.source_editor.editor_of(used_variables)
        usages = window.source_sync.find_usages(used_variables, "shared")
        assert len(usages) == 2

        # WHEN
        editor.usagesRequested.emit("shared", QPoint(0, 0))

        # THEN
        popup = window.source_editor._usages_popup
        assert popup.tree.topLevelItemCount() == 1
        assert popup.tree.topLevelItem(0).text(0) == f"devices/test_device/editor.jsonl  ({len(usages)})"
        items = popup.usage_items()
        assert [item.data(0, Qt.ItemDataRole.UserRole) for item in items] == usages
        popup.choose(items[1])
        assert window.source_editor.current_file == usages[1].path
        assert window.source_editor.current_editor.cursor_line_column[0] == usages[1].line

    def test_a_key_is_ctrl_clickable_in_a_variable_file(self, used_variables, window):
        # GIVEN
        window.file_tree_widget.openRequested.emit(used_variables)
        editor = window.source_editor.editor_of(used_variables)
        editor.resize(500, 200)
        editor.show()
        requests = []
        editor.usagesRequested.connect(lambda name, position: requests.append(name))
        position = QPoint(editor.fontMetrics().horizontalAdvance("sin") + 2, editor.fontMetrics().height() * 3 // 2)

        # WHEN
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)

        # THEN
        assert requests == ["single"]


class TestUnusedVariables(TestBase):
    def test_unused_variables_are_dimmed_and_explained(self, unused_file, window):
        # WHEN
        window.file_tree_widget.openRequested.emit(unused_file)

        # THEN
        editor = window.source_editor.editor_of(unused_file)
        assert [(hint.line, hint.column) for hint in editor._hints] == [(1, 0), (2, 0)]
        assert len(editor._hint_selections()) == 2
        issues = editor.hover.card_content_at(QPoint(5, 5)).issues
        assert issues == [(Severity.HINT, "Not used: no file of any device uses unused_one")]

    def test_the_hints_are_hidden_while_the_text_differs_from_the_analyzed_one(self, unused_file, window):
        # GIVEN
        window.file_tree_widget.openRequested.emit(unused_file)
        editor = window.source_editor.editor_of(unused_file)

        # WHEN: a line is added above
        editor.set_text("\n" + unused_file.read_text())
        editor.textEdited.emit()
        # THEN: their lines would be wrong
        assert editor._hints == []

        # WHEN: it is the text again
        editor.set_text(unused_file.read_text())
        editor.textEdited.emit()
        # THEN
        assert len(editor._hints) == 2


class TestOpening(TestBase):
    def test_double_click_in_the_tree_opens_the_file_next_to_the_rendered_view(self, window, editor_file):
        # WHEN
        window.file_tree_widget.openRequested.emit(editor_file)

        # THEN
        assert window.source_editor.current_file == editor_file
        assert window.code_view.mode.value == "split"
        assert window.source_editor.current_editor.toPlainText() == EDITOR_JSONL

    def test_the_rendered_view_shows_the_objects_of_the_open_file(self, window, editor_file):
        # GIVEN
        [component] = window.session.components
        assert window.file_rendered.view.toPlainText() == ""

        # WHEN
        window.file_tree_widget.openRequested.emit(editor_file)

        # THEN
        lines = window.file_rendered.view.toPlainText().splitlines()
        assert [json.loads(line)["id"] for line in lines] == [
            obj["id"] for obj in window.session.working_objects[component.key]
        ]

    def test_the_rendered_view_follows_the_current_tab(self, window, editor_file, cfg_root):
        # GIVEN
        window.file_tree_widget.openRequested.emit(editor_file)
        other = cfg_root / "other.cmd"
        other.write_text("page 1\n")

        # WHEN: a file without objects in the draft
        window.file_tree_widget.openRequested.emit(other)

        # THEN
        assert window.file_rendered.view.toPlainText() == ""
        assert window.file_rendered.view.placeholderText() == "No objects of this file in the draft."

    def test_the_rendered_view_says_when_it_is_out_of_date(self, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(editor_file)
        editor = window.source_editor.current_editor
        assert not window.file_rendered.out_of_date

        # WHEN: unsaved text
        editor.set_text(EDITOR_JSONL.replace('"x": 10', '"x": 55'))
        editor.textEdited.emit()
        # THEN
        assert window.file_rendered.out_of_date

        # WHEN: saved
        window.source_editor.save(editor_file)
        # THEN: once the draft is loaded from the saved file
        wait_until(lambda: not window.file_rendered.out_of_date)
        assert x_of_label(window) == 55

    def test_selecting_an_object_shows_its_line(self, window, editor_file):
        # GIVEN
        window.code_view.set_mode(window.code_view.mode.__class__.SPLIT)
        [component] = window.session.components
        button = window.session.working_objects[component.key][1]

        # WHEN
        window.page_layout_editor_widget.page_preview_widget.select_object(button)

        # THEN
        assert window.source_editor.current_file == editor_file
        assert window.source_editor.current_editor.cursor_line_column[0] == 2
        assert window.source_editor.current_editor.flashed_lines == (2, 2)

    def test_selecting_an_object_highlights_its_lines_in_the_rendered_jsonl(self, window):
        # GIVEN
        [component] = window.session.components
        label, button = window.session.working_objects[component.key]
        preview = window.page_layout_editor_widget.jsonl_preview

        # WHEN
        window.page_layout_editor_widget.page_preview_widget.select_object(button)
        selected = [preview.document().findBlockByNumber(line).text() for line in preview.selected_lines]
        window.page_layout_editor_widget.page_preview_widget.scene().clearSelection()

        # THEN
        assert [json.loads(text)["id"] for text in selected] == [2]
        assert preview.selected_lines == []

    def test_nothing_opens_while_the_source_is_hidden_or_the_draft_has_changes(self, window):
        # GIVEN
        [component] = window.session.components
        label, button = window.session.working_objects[component.key]

        # WHEN: rendered only
        window.page_layout_editor_widget.page_preview_widget.select_object(label)
        # THEN
        assert window.source_editor.open_files == []

        # WHEN: a draft with changes
        window.code_view.set_mode(window.code_view.mode.__class__.SPLIT)
        window.session.set_source_value(label, "x", 20)
        window.page_layout_editor_widget.page_preview_widget.select_object(button)
        # THEN
        assert window.source_editor.open_files == []

    def test_ctrl_click_on_a_variable_opens_its_definition(self, window, editor_file, cfg_root):
        # GIVEN
        variables = cfg_root / "devices" / "test_device" / "vars.yaml"
        variables.write_text("header:\n  bar:\n    height: 27\n")
        window.file_tree_widget.openRequested.emit(editor_file)
        editor = window.source_editor.editor_of(editor_file)
        assert window.source_sync.find_definition(editor_file, "header.bar.height").line == 3

        # WHEN
        editor.definitionRequested.emit("header.bar")

        # THEN
        assert window.source_editor.current_file == variables.resolve()
        assert window.source_editor.current_editor.cursor_line_column[0] == 2

    def test_files_that_cannot_be_opened_are_reported(self, window, cfg_root):
        failures = []
        window.status.failed.connect(lambda description, error: failures.append(description))
        (cfg_root / "bad.jsonl").write_bytes(b"\xff\xfe")
        window.file_tree_widget.openRequested.emit(cfg_root / "bad.jsonl")
        assert failures == ["Opening bad.jsonl"]


class TestSaving(TestBase):
    def test_saving_a_file_updates_the_pages(self, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(editor_file)
        editor = window.source_editor.current_editor
        editor.set_text(EDITOR_JSONL.replace('"x": 10', '"x": 55'))
        editor.textEdited.emit()
        messages = []
        window.status.succeeded.connect(messages.append)

        # WHEN
        assert window.source_editor.save()

        # THEN
        wait_until(lambda: x_of_label(window) == 55)
        assert "Saved editor.jsonl" in messages
        assert window.source_editor.dirty_files() == []
        assert editor_file.read_text().count('"x": 55') == 1

    def test_saving_the_draft_updates_its_open_files(self, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(editor_file)
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        assert window.draft_actions.save()

        # THEN
        wait_until(lambda: window.source_editor.current_editor.toPlainText() == editor_file.read_text())
        assert '"x": 20' in window.source_editor.current_editor.toPlainText()

    def test_the_own_save_is_no_change_on_disk(self, window, editor_file):
        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text("{}\n")
        window.source_editor.current_editor.textEdited.emit()
        window.source_editor.save()
        wait_until(lambda: window.session is not None and window.session.is_loaded)
        from PyQt6.QtTest import QTest

        QTest.qWait(800)
        assert window.source_editor.dirty_files() == []
        assert not window.source_editor._pages[editor_file].banner.isVisible()

    def test_saving_with_a_changed_draft_offers_the_reload_banner(self, window, editor_file):
        # GIVEN
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)
        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text(EDITOR_JSONL.replace('"x": 10', '"x": 55'))
        window.source_editor.current_editor.textEdited.emit()

        # WHEN
        window.source_editor.save()

        # THEN
        assert not window.disk_changes_banner.isHidden()
        assert x_of_label(window) == 20


class TestPartMode(TestBase):
    @pytest.fixture
    def part_file(self, cfg_root) -> Path:
        # written before the window loads the device
        part = cfg_root / "devices" / "test_device" / "dot.jsonl"
        part.write_text('{"page": 9, "id": "{{ id }}", "obj": "label", "text": "{{ id }}"}\n')
        editor = cfg_root / "devices" / "test_device" / "editor.jsonl"
        editor.write_text(editor.read_text() + '{"!include": "devices/test_device/dot.jsonl", "for": {"id": [20, 21]}}\n')
        return part.resolve()

    def test_the_files_tree_starts_it_and_saving_writes_the_part(self, part_file, window, editor_file):
        # GIVEN
        editor = window.page_layout_editor_widget
        before = editor_file.read_text()

        # WHEN
        window.file_tree_widget.editPartRequested.emit(part_file)
        [first, _second] = window.session.part_instances(part_file)
        [dot] = window.session.objects_of_instance(first)
        window.session.set_source_value(dot, "text", "#{{ id }}")

        # THEN
        wait_until(lambda: (gui_state(window.cfg_root).get("device") or {}).get("part_mode"))
        state = gui_state(window.cfg_root)["device"]
        assert state["part_mode"]["part"] == "devices/test_device/dot.jsonl"
        assert state["new_objects_file"] == "devices/test_device/dot.jsonl"
        assert state["draft"]["files"] == [
            {"file": "devices/test_device/dot.jsonl", "changed": ["p9b{{ id }}"], "added": [], "deleted": []}
        ]

        # WHEN
        assert window.draft_actions.save()

        # THEN: the part goes on in part mode after the reload
        assert part_file.read_text() == '{"page": 9, "id": "{{ id }}", "obj": "label", "text": "#{{ id }}"}\n'
        assert editor_file.read_text() == before
        wait_until(lambda: window.session.is_loaded and not window.session.is_dirty)
        assert window.session.part_mode == first
        assert not editor.part_bar.isHidden()


CARD_JSONL = '{"page": "{{ card.page }}", "id": "{{ card.id }}", "obj": "label", "x": 5, "text": "{{ title }}"}\n'


class TestPartAlone(TestBase):
    @pytest.fixture
    def card_file(self, cfg_root) -> Path:
        # written before the window loads the device; no page includes it
        part = cfg_root / "devices" / "test_device" / "card.jsonl"
        part.write_text(CARD_JSONL)
        return part.resolve()

    def test_the_text_editor_shows_a_part_on_its_own_and_saving_writes_only_the_part(self, card_file, window, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        # GIVEN
        editor = window.page_layout_editor_widget
        device_session = window.session
        window.file_tree_widget.openRequested.emit(card_file)
        [edit_part] = [
            action
            for action in window.source_editor.current_editor.context_menu(QPoint(0, 0)).actions()
            if action.text() == "Edit the part"
        ]

        # WHEN
        edit_part.trigger()

        # THEN: instead of the pages, with a placeholder for each variable
        alone = window.part_alone
        assert window.session is alone and editor.session is alone
        assert [obj.get("id") for obj in editor.page_objects] == [1]
        assert "on its own" in editor.part_bar.title.text()
        assert "No page of test_device includes it" in editor.part_bar.hint.text()
        wait_until(lambda: ((gui_state(window.cfg_root).get("device") or {}).get("part_mode") or {}).get("alone"))
        assert gui_state(window.cfg_root)["device"]["files"] == []

        # WHEN: vars of its own, and a change of the part
        [label] = editor.page_objects
        alone.set_directive_value(label, "vars", {"card": {"page": 9, "id": 7}, "title": "Hello"})
        alone.set_source_value(label, "x", 6)

        # THEN
        assert (label["page"], label["id"], label["text"]) == (9, 7, "Hello")
        assert window.action_save.isEnabled()
        assert window.draft_actions.save()
        assert card_file.read_text() == CARD_JSONL.replace('"x": 5', '"x": 6')
        assert not window.session.is_dirty and window.part_alone is alone

        # WHEN: another change, then Done: discarded
        alone.set_source_value(label, "x", 7)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
        editor.part_bar.done.click()

        # THEN: back on the pages of the device, which don't have the part
        assert window.part_alone is None
        assert window.session is device_session and editor.session is device_session
        assert editor.part_bar.isHidden()
        assert card_file.read_text() == CARD_JSONL.replace('"x": 5', '"x": 6')

    def test_done_with_changes_can_be_cancelled(self, card_file, window, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        # GIVEN
        window.file_tree_widget.editPartRequested.emit(card_file)
        alone = window.part_alone
        [label] = window.page_layout_editor_widget.page_objects
        alone.set_source_value(label, "x", 7)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)

        # WHEN
        window.page_layout_editor_widget.part_bar.done.click()

        # THEN
        assert window.part_alone is alone
        assert "card.jsonl (part)" in window._dirty_draft_names()

    def test_a_part_on_its_own_follows_a_change_on_disk(self, card_file, window):
        # GIVEN
        window.file_tree_widget.editPartRequested.emit(card_file)

        # WHEN
        card_file.write_text(CARD_JSONL.replace('"x": 5', '"x": 50'))

        # THEN: still on its own
        wait_until(lambda: window.part_alone is not None and window.page_layout_editor_widget.page_objects[0]["x"] == 50)
        assert window.page_layout_editor_widget.session is window.part_alone
        assert window.part_alone.part_mode is not None

    def test_a_part_the_pages_include_is_edited_on_the_pages(self, card_file, window, cfg_root):
        # GIVEN: a part on its own
        dot = cfg_root / "devices" / "test_device" / "dot.jsonl"
        dot.write_text('{"page": 9, "id": "{{ id }}", "obj": "label"}\n')
        editor_file = cfg_root / "devices" / "test_device" / "editor.jsonl"
        editor_file.write_text(editor_file.read_text() + '{"!include": "devices/test_device/dot.jsonl", "vars": {"id": 30}}\n')
        wait_until(lambda: window.session is not None and window.session.part_instances(dot))
        window.file_tree_widget.editPartRequested.emit(card_file)
        assert window.part_alone is not None

        # WHEN
        window.file_tree_widget.editPartRequested.emit(dot)

        # THEN
        assert window.part_alone is None
        assert window.session.part_mode.part == dot.resolve()

    def test_a_page_file_is_not_shown_as_a_part(self, window, editor_file):
        # GIVEN
        failures = []
        window.status.failed.connect(lambda *args: failures.append(args))

        # WHEN
        window.page_layout_editor_widget.edit_part(editor_file)

        # THEN
        assert window.part_alone is None
        assert failures == [("Editing the part editor.jsonl", "it is a page file of the device: edit its objects on the page")]


class TestChangesOnDisk(TestBase):
    def test_an_open_file_follows_changes_made_elsewhere(self, window, editor_file):
        window.file_tree_widget.openRequested.emit(editor_file)

        editor_file.write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        wait_until(lambda: '"x": 77' in window.source_editor.current_editor.toPlainText())
        wait_until(lambda: x_of_label(window) == 77)

    def test_changes_made_elsewhere_to_a_file_with_text_changes_conflict(self, window, editor_file):
        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text("mine")
        window.source_editor.current_editor.textEdited.emit()

        editor_file.write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        wait_until(lambda: window.source_editor.buffer_of(editor_file).conflict)
        wait_until(lambda: (gui_state(window.cfg_root).get("editor") or {}).get("files", [{}])[0].get("conflict"))
        assert window.source_editor.current_editor.toPlainText() == "mine"


class TestMarkersAndCompletion(TestBase):
    def test_problems_of_the_page_are_marked_in_the_source(self, window, editor_file):
        # GIVEN
        editor_file.write_text(EDITOR_JSONL + '{"page": 9, "id": 3, "obj": "btn", "x": 470, "y": 0, "w": 100, "h": 20}\n')
        window.file_tree_widget.openRequested.emit(editor_file)

        # THEN
        wait_until(lambda: window.source_editor.current_editor._app_markers)
        [marker] = window.source_editor.current_editor._app_markers
        assert marker.line == 3
        assert "outside of the screen" in marker.message

    def test_errors_of_the_directives_are_marked_where_they_are(self, cfg_root, create_window, editor_file):
        # GIVEN: written before the window loads the device
        editor_file.write_text(EDITOR_JSONL + '{"!include": "common/nope.jsonl"}\n')
        window = create_window()
        wait_until(lambda: window.devices)
        window.on_device_selected("test_device")
        wait_until(lambda: window.session is not None and window.session.is_loaded)

        # WHEN
        window.file_tree_widget.openRequested.emit(editor_file)

        # THEN
        wait_until(lambda: window.source_editor.current_editor._app_markers)
        [marker] = window.source_editor.current_editor._app_markers
        assert marker.line == EDITOR_JSONL.count("\n") + 1
        assert marker.severity == Severity.ERROR
        assert marker.message.endswith("The file to include doesn't exist: common/nope.jsonl")

    def test_the_page_editor_can_show_a_file_at_a_line(self, window, editor_file):
        # WHEN
        window.page_layout_editor_widget.openSourceRequested.emit(editor_file, 2)

        # THEN
        assert window.source_editor.current_file == editor_file
        assert window.source_editor.current_editor.cursor_line_column[0] == 2

    def test_variables_of_the_files_of_the_device_are_offered(self, window, editor_file):
        names = window.source_sync.variables_of_file(editor_file)
        assert names
        assert all(not name.startswith("{{") for name in names)
        assert window.source_sync.variables_of_file(editor_file.parent / "other.jsonl") == []
        assert window.source_sync.variables_of_file(editor_file.parent.parent.parent / "nothing.yaml") == []


class TestSessionAndState(TestBase):
    def test_open_files_are_remembered(self, window, editor_file):
        window.file_tree_widget.openRequested.emit(editor_file)
        assert window.ui_session.session.open_files == ["devices/test_device/editor.jsonl"]
        assert window.ui_session.session.current_file == "devices/test_device/editor.jsonl"

        window.source_editor.close_all(ask=False)
        assert window.ui_session.session.open_files == []

        window.ui_session.session.open_files = ["devices/test_device/editor.jsonl", "gone.jsonl"]
        window.ui_session.session.current_file = "devices/test_device/editor.jsonl"
        window.source_sync.restore_open_files()
        assert window.source_editor.open_files == [editor_file]
        assert window.source_editor.current_file == editor_file

    def test_the_state_describes_the_text_editor(self, window, editor_file):
        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text("{")
        window.source_editor.current_editor.textEdited.emit()
        window.source_editor.current_editor.go_to(1, 1)

        # the state file may be written before the tab is in it ("files": [])
        wait_until(lambda: ((gui_state(window.cfg_root).get("editor") or {}).get("files") or [{}])[0].get("dirty"))

        state = gui_state(window.cfg_root)
        assert state["editor"]["mode"] == "split"
        assert state["editor"]["current"] == "devices/test_device/editor.jsonl"
        [tab] = state["editor"]["files"]
        assert tab["file"] == "devices/test_device/editor.jsonl"
        assert tab["dirty"] is True and tab["conflict"] is False
        json.dumps(state)

    def test_closing_the_window_asks_about_unsaved_text(self, window, editor_file, monkeypatch):
        from PyQt6.QtGui import QCloseEvent
        from PyQt6.QtWidgets import QMessageBox

        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text("changed")
        window.source_editor.current_editor.textEdited.emit()
        questions = []

        def answer(parent, title, text, *args):
            questions.append(text)
            return QMessageBox.StandardButton.Cancel

        monkeypatch.setattr(QMessageBox, "question", answer)
        event = QCloseEvent()
        window.closeEvent(event)

        assert not event.isAccepted()
        assert "editor.jsonl (text editor)" in questions[0]


class TestCursorSelectsObject(TestBase):
    def test_the_object_of_the_cursor_is_selected_in_the_preview(self, window, editor_file):
        # GIVEN
        [component] = window.session.components
        label, button = window.session.working_objects[component.key]

        window.source_editor.open_file(editor_file, focus=False)

        # WHEN
        window.source_editor.objectAtCursorChanged.emit(editor_file, 1)

        # THEN
        selected = window.page_layout_editor_widget.page_preview_widget.selected_items()
        assert [item.obj_data for item in selected] == [button]

        # WHEN
        window.source_editor.objectAtCursorChanged.emit(editor_file, 0)
        selected = window.page_layout_editor_widget.page_preview_widget.selected_items()
        assert [item.obj_data for item in selected] == [label]

    def test_it_does_not_jump_back_to_the_first_line_of_the_object(self, window, editor_file):
        # GIVEN
        window.code_view.set_mode(window.code_view.mode.__class__.SPLIT)
        window.file_tree_widget.openRequested.emit(editor_file)
        editor = window.source_editor.current_editor
        editor.set_text('{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}\n')
        editor.go_to(1, 20)
        [component] = window.session.components
        buffer = window.source_editor.buffer_of(editor_file)
        assert buffer.text == component.content

        # WHEN: the preview selects the object of the cursor
        window.page_layout_editor_widget.page_preview_widget.select_object(window.session.working_objects[component.key][0])

        # THEN
        assert editor.cursor_line_column == (1, 21)

    def test_nothing_happens_for_text_that_differs_from_the_draft_or_without_object(self, window, editor_file):
        [component] = window.session.components
        window.file_tree_widget.openRequested.emit(editor_file)
        window.source_editor.current_editor.set_text(EDITOR_JSONL + "{}\n")
        window.source_editor.current_editor.textEdited.emit()
        window.source_editor.objectAtCursorChanged.emit(editor_file, 1)
        assert window.page_layout_editor_widget.page_preview_widget.selected_items() == []

        window.source_editor.keep_mine(editor_file)
        window.source_editor.objectAtCursorChanged.emit(editor_file, -1)
        window.source_editor.objectAtCursorChanged.emit(window.source_editor.current_file.parent / "nope.jsonl", 0)
        assert window.page_layout_editor_widget.page_preview_widget.selected_items() == []
        assert component is not None

    def test_an_object_on_another_page_switches_the_page(self, window, editor_file):
        editor_file.write_text(EDITOR_JSONL + '{"page": 8, "id": 1, "obj": "btn", "text": "C"}\n')
        wait_until(lambda: len(window.session.working_objects[window.session.components[0].key]) == 3)
        [component] = window.session.components

        window.source_editor.open_file(editor_file, focus=False)
        window.source_editor.objectAtCursorChanged.emit(editor_file, 2)

        assert window.page_layout_editor_widget.current_index == 8
        selected = window.page_layout_editor_widget.page_preview_widget.selected_items()
        assert [item.obj_data["text"] for item in selected] == ["C"]
        assert component is not None


class TestMistakesDoNotCrash(TestBase):
    def test_a_template_that_uses_a_renamed_object_is_kept_as_written(self, window, editor_file):
        # GIVEN: object 2 positions itself relative to object 1
        content = EDITOR_JSONL.replace('"text": "B"', '"text": "B", "x": "{{ p9b1.x + 5 }}"')
        editor_file.write_text(content)
        wait_until(lambda: window.session.working_objects[window.session.components[0].key][1].get("x") == 15)

        # WHEN: object 1 gets another id, so p9b1 is gone
        editor_file.write_text(content.replace('"id": 1,', '"id": 7,'))

        # THEN: the reload works, the template stays as written and is reported
        wait_until(lambda: window.session.working_objects[window.session.components[0].key][1].get("x") == "{{ p9b1.x + 5 }}")
        wait_until(lambda: any("x is not a number" in p.message for p in window.page_layout_editor_widget.problems))


class TestUsagesPopup(TestBase):
    def test_selecting_a_usage_shows_the_code_around_it(self, used_variables, window, editor_file):
        # GIVEN
        window.file_tree_widget.openRequested.emit(used_variables)
        usages = window.source_sync.find_usages(used_variables, "shared")
        popup = show_usages_popup(window, usages, window.cfg_root, QPoint(0, 0), lambda usage: None)
        lines = editor_file.read_text(encoding="utf-8").splitlines()

        # WHEN
        popup.tree.setCurrentItem(popup.usage_items()[1])

        # THEN: the lines around the line of the usage
        assert lines[usages[1].line - 1].strip() in popup.preview_text()
        popup.close()

    def test_a_usage_is_chosen_by_activating_it_not_by_selecting_it(self, window, editor_file):
        # GIVEN
        chosen = []
        usages = [Usage(editor_file, 1, 0, 1), Usage(editor_file, 2, 0, 1)]
        popup = show_usages_popup(window, usages, window.cfg_root, QPoint(0, 0), chosen.append)

        # WHEN
        popup.tree.setCurrentItem(popup.usage_items()[1])

        # THEN
        assert chosen == []

        # WHEN
        popup.tree.itemActivated.emit(popup.usage_items()[1], 0)

        # THEN
        assert chosen == [usages[1]]

    def test_many_usages_do_not_make_the_popup_bigger_than_the_screen(self, window, editor_file):
        usages = [Usage(editor_file, 1, 0, 1) for _ in range(300)]
        popup = show_usages_popup(window, usages, window.cfg_root, QPoint(0, 0), lambda usage: None)
        assert popup.height() <= 520
        assert popup.tree.verticalScrollBar().maximum() > 0
        popup.close()

    def test_activating_a_file_folds_it(self, window, editor_file):
        popup = show_usages_popup(window, [Usage(editor_file, 1, 0, 1)], window.cfg_root, QPoint(0, 0), lambda usage: None)
        file_item = popup.tree.topLevelItem(0)
        popup.tree.itemActivated.emit(file_item, 0)
        assert not file_item.isExpanded()
        popup.close()


class TestUsagesPopupColors(TestBase):
    def test_text_that_can_not_be_read_on_the_mark_gets_a_readable_color(self):
        from PyQt6.QtGui import QColor

        from openhasp_config_manager.gui.qt.widgets.source.usages_popup import _contrast, _readable_on

        background = QColor("#3b6070")
        readable = _readable_on(QColor("#795E26"), background, QColor("#222222"))
        assert _contrast(readable, background) >= 4.5
        assert _readable_on(QColor("#FFFFFF"), background, QColor("#222222")) == QColor("#FFFFFF")
