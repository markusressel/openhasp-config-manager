from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.helpers import EDITOR_JSONL, create_editor_cfg_root, gui_state, qwait, wait_until, x_of_label

@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return create_editor_cfg_root(tmp_path)


@pytest.fixture
def window(create_window):
    window = create_window()
    wait_until(lambda: window.devices)
    window.on_device_selected("test_device")
    wait_until(lambda: window.session is not None and window.session.is_loaded)
    return window


class TestChangesOnDisk(TestBase):
    def test_a_draft_without_changes_follows_the_files(self, window, cfg_root):
        # GIVEN
        window.page_layout_editor_widget.set_page_index(9)

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        # THEN
        wait_until(lambda: x_of_label(window) == 77)
        assert window.page_layout_editor_widget.current_index == 9
        assert window.disk_changes_banner.isHidden()

    def test_a_draft_with_changes_is_kept_and_a_banner_offers_to_reload(self, window, cfg_root):
        # GIVEN
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        # THEN
        wait_until(lambda: not window.disk_changes_banner.isHidden())
        assert x_of_label(window) == 20
        assert window.session.is_dirty

        # WHEN
        window.disk_changes_banner.reloadRequested.emit()

        # THEN
        wait_until(lambda: window.session is not None and window.session.is_loaded and not window.session.is_dirty)
        wait_until(lambda: x_of_label(window) == 77)
        assert window.disk_changes_banner.isHidden()

    def test_changes_of_another_device_do_not_affect_a_draft(self, window, cfg_root):
        # GIVEN
        other = cfg_root / "devices" / "other_device"
        other.mkdir()
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        (other / "page.jsonl").write_text(EDITOR_JSONL)
        qwait(900)

        # THEN
        assert window.disk_changes_banner.isHidden()
        assert x_of_label(window) == 20

    def test_saving_is_not_a_change_by_someone_else(self, window, monkeypatch):
        # GIVEN
        reloads = []
        monkeypatch.setattr(window, "_reload_changed_files", lambda paths: reloads.append(paths))
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        assert window.save_draft()
        wait_until(lambda: window.session is not None and window.session.is_loaded)
        qwait(900)

        # THEN
        assert reloads == []
        assert window.disk_changes_banner.isHidden()
        assert x_of_label(window) == 20

    def test_a_file_that_can_not_be_loaded_keeps_what_is_shown(self, window, cfg_root):
        # GIVEN
        failures = []
        window.status.failed.connect(lambda description, error: failures.append(description))

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text('{"page": 9, "id": }')

        # THEN
        wait_until(lambda: failures)
        assert window.device is not None
        assert x_of_label(window) == 10

        # WHEN: an object is not closed yet (written halfway)
        failures.clear()
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL + '{"page": 9, "id": 3,')

        # THEN
        wait_until(lambda: failures)
        assert x_of_label(window) == 10

        # WHEN: the file is fixed
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 5'))

        # THEN
        wait_until(lambda: x_of_label(window) == 5)


class TestGuiStateFile(TestBase):
    def test_the_state_describes_what_is_open(self, window, cfg_root):
        # GIVEN
        window.page_layout_editor_widget.set_page_index(9)
        window.page_layout_editor_widget.set_edit_mode(True)
        label = window.session.working_objects[window.session.components[0].key][0]
        window.page_layout_editor_widget.page_preview_widget.select_object(label)

        # THEN
        wait_until(lambda: (gui_state(cfg_root).get("device") or {}).get("selection"))
        state = gui_state(cfg_root)
        assert state["running"] is True
        assert state["devices"] == ["test_device"]
        device = state["device"]
        assert device["name"] == "test_device"
        assert device["page"] == 9
        assert device["pages"] == [9]
        assert device["edit_mode"] is True
        assert device["selection"][0]["name"] == "p9b1"
        assert device["selection"][0]["line"] == 1
        assert device["selection"][0]["rendered"]["x"] == 10
        assert device["selection"][0]["source"]["x"] == 10
        assert state["check_command"] == f"openhasp-config-manager check -c {cfg_root} --json"
        assert device["draft"] == {"modified": False, "files": []}
        assert state["load_error"] is None

    def test_the_state_reports_the_draft_and_changes_on_disk(self, window, cfg_root):
        # WHEN
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)
        window.page_layout_editor_widget.dirtyChanged.emit(True)
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        # THEN
        wait_until(lambda: gui_state(cfg_root).get("files_changed_on_disk"))
        state = gui_state(cfg_root)
        assert state["files_changed_on_disk"] == ["devices/test_device/editor.jsonl"]
        assert state["device"]["draft"]["modified"] is True
        assert state["device"]["draft"]["files"][0]["changed"] == ["p9b1"]

    def test_the_state_reports_why_a_file_can_not_be_loaded(self, window, cfg_root):
        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text('{"page": 9, "id": }')

        # THEN
        wait_until(lambda: gui_state(cfg_root).get("load_error"))
        state = gui_state(cfg_root)
        assert "editor.jsonl" in state["load_error"]["message"]
        assert state["last_operation"]["ok"] is False

    def test_the_state_says_when_the_gui_is_closed(self, window, cfg_root):
        # WHEN
        window.quit_discarding_drafts()

        # THEN
        state = gui_state(cfg_root)
        assert state["running"] is False
        qwait(500)
        assert gui_state(cfg_root)["running"] is False
