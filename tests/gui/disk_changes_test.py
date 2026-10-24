import shutil
from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.main_window_test import _wait_until, create_window  # noqa: F401 (a fixture)

EDITOR_JSONL = """{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{"page": 9, "id": 2, "obj": "btn", "text": "B"}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    pytest.importorskip("watchdog")
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device = root / "devices" / "test_device"
    (device / "editor.jsonl").write_text(EDITOR_JSONL)
    (device / "boot.cmd").write_text("run L:/editor.jsonl\n")
    return root


def _x_of_label(window) -> int:
    [component] = window.session.components
    return window.session.working_objects[component.key][0]["x"]


@pytest.fixture
def window(create_window):  # noqa: F811
    window = create_window()
    _wait_until(lambda: window.devices)
    window.on_device_selected("test_device")
    _wait_until(lambda: window.session is not None and window.session.is_loaded)
    return window


def _qwait(ms: int):
    from PyQt6.QtTest import QTest

    QTest.qWait(ms)


class TestChangesOnDisk(TestBase):
    def test_a_draft_without_changes_follows_the_files(self, window, cfg_root):
        # GIVEN
        window.page_layout_editor_widget.set_page_index(9)

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        # THEN
        _wait_until(lambda: _x_of_label(window) == 77)
        assert window.page_layout_editor_widget.current_index == 9
        assert window.disk_changes_banner.isHidden()

    def test_a_draft_with_changes_is_kept_and_a_banner_offers_to_reload(self, window, cfg_root):
        # GIVEN
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 77'))

        # THEN
        _wait_until(lambda: not window.disk_changes_banner.isHidden())
        assert _x_of_label(window) == 20
        assert window.session.is_dirty

        # WHEN
        window.disk_changes_banner.reloadRequested.emit()

        # THEN
        _wait_until(lambda: window.session is not None and window.session.is_loaded and not window.session.is_dirty)
        _wait_until(lambda: _x_of_label(window) == 77)
        assert window.disk_changes_banner.isHidden()

    def test_changes_of_another_device_do_not_affect_a_draft(self, window, cfg_root):
        # GIVEN
        other = cfg_root / "devices" / "other_device"
        other.mkdir()
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        (other / "page.jsonl").write_text(EDITOR_JSONL)
        _qwait(900)

        # THEN
        assert window.disk_changes_banner.isHidden()
        assert _x_of_label(window) == 20

    def test_saving_is_not_a_change_by_someone_else(self, window, monkeypatch):
        # GIVEN
        reloads = []
        monkeypatch.setattr(window, "_reload_changed_files", lambda paths: reloads.append(paths))
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)

        # WHEN
        assert window.save_draft()
        _wait_until(lambda: window.session is not None and window.session.is_loaded)
        _qwait(900)

        # THEN
        assert reloads == []
        assert window.disk_changes_banner.isHidden()
        assert _x_of_label(window) == 20

    def test_a_file_that_can_not_be_loaded_keeps_what_is_shown(self, window, cfg_root):
        # GIVEN
        failures = []
        window.status.failed.connect(lambda description, error: failures.append(description))

        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text('{"page": 9, "id": }')

        # THEN
        _wait_until(lambda: failures)
        assert window.device is not None
        assert _x_of_label(window) == 10

        # WHEN: an object is not closed yet (written halfway)
        failures.clear()
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL + '{"page": 9, "id": 3,')

        # THEN
        _wait_until(lambda: failures)
        assert _x_of_label(window) == 10

        # WHEN: the file is fixed
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 5'))

        # THEN
        _wait_until(lambda: _x_of_label(window) == 5)


def _state(cfg_root: Path) -> dict:
    import json

    try:
        return json.loads((cfg_root / ".openhasp-config-manager" / "gui-state.json").read_text())
    except FileNotFoundError:
        return {}


class TestGuiStateFile(TestBase):
    def test_the_state_describes_what_is_open(self, window, cfg_root):
        # GIVEN
        window.page_layout_editor_widget.set_page_index(9)
        window.page_layout_editor_widget.set_edit_mode(True)
        label = window.session.working_objects[window.session.components[0].key][0]
        window.page_layout_editor_widget.page_preview_widget.select_object(label)

        # THEN
        _wait_until(lambda: (_state(cfg_root).get("device") or {}).get("selection"))
        state = _state(cfg_root)
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
        _wait_until(lambda: _state(cfg_root).get("files_changed_on_disk"))
        state = _state(cfg_root)
        assert state["files_changed_on_disk"] == ["devices/test_device/editor.jsonl"]
        assert state["device"]["draft"]["modified"] is True
        assert state["device"]["draft"]["files"][0]["changed"] == ["p9b1"]

    def test_the_state_reports_why_a_file_can_not_be_loaded(self, window, cfg_root):
        # WHEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text('{"page": 9, "id": }')

        # THEN
        _wait_until(lambda: _state(cfg_root).get("load_error"))
        state = _state(cfg_root)
        assert "editor.jsonl" in state["load_error"]["message"]
        assert state["last_operation"]["ok"] is False

    def test_the_state_says_when_the_gui_is_closed(self, window, cfg_root):
        # WHEN
        window.quit_discarding_drafts()

        # THEN
        state = _state(cfg_root)
        assert state["running"] is False
        _qwait(500)
        assert _state(cfg_root)["running"] is False
