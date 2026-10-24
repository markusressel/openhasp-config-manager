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

        # WHEN: the file is fixed
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(EDITOR_JSONL.replace('"x": 10', '"x": 5'))

        # THEN
        _wait_until(lambda: _x_of_label(window) == 5)
