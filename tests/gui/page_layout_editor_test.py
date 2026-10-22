import shutil
import threading
from pathlib import Path

import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft_files import load_device
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests import TestBase

EDITOR_JSONL = """{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{"page": 9, "id": 2, "obj": "btn", "text": "B"}
{"page": 1, "id": 50, "obj": "label", "text": "E"}
"""


class _Plate:
    """Records what the editor sends to the plate (from the background loop)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []

    def record(self, *call):
        with self._lock:
            self._calls.append(call)

    @property
    def calls(self):
        with self._lock:
            return list(self._calls)

    def clear(self):
        with self._lock:
            self._calls.clear()


@pytest.fixture
def plate(monkeypatch) -> _Plate:
    plate = _Plate()

    def recording(name):
        async def method(client, *args):
            plate.record(name, *args)

        return method

    for name in ["clear_page", "jsonl", "set_page", "delete_object_id", "restore_from_files"]:
        monkeypatch.setattr(OpenHaspClient, name, recording(name))
    return plate


@pytest.fixture
def editor(qapp, async_loop, plate, tmp_path, monkeypatch):
    from openhasp_config_manager.gui.qt.operations import OperationStatus
    from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData, page_layout_editor
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget

    monkeypatch.setattr(page_layout_editor, "SEND_DELAY_SECONDS", 0)

    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device_dir = root / "devices" / "test_device"
    (device_dir / "editor.jsonl").write_text(EDITOR_JSONL)
    (device_dir / "boot.cmd").write_text("run L:/home_page.jsonl\nrun L:/editor.jsonl\n")
    loaded = load_device(_create_config_manager(root, tmp_path / "output"), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)

    widget = PageLayoutEditorWidget(status=OperationStatus())
    widget.set_data(
        session=session,
        device_pages_data=OpenHaspDevicePagesData(
            device=loaded.device, name=loaded.cmd_component.name, jsonl_components=loaded.jsonl_components
        ),
        page=9,
    )
    return widget


def _wait_until(condition, timeout_ms: int = 2000):
    from PyQt6.QtTest import QTest

    for _ in range(timeout_ms // 10):
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("timed out")


def _sent_objects(plate: _Plate):
    return [(call[1].get("page"), call[1].get("id")) for call in plate.calls if call[0] == "jsonl"]


def _object(editor, obj_id: int):
    return next(obj for obj in editor.page_objects if obj.get("page") == 9 and obj.get("id") == obj_id)


class TestLivePreview(TestBase):
    def _start(self, editor, plate):
        editor.action_live_preview.setChecked(True)
        _wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))

    def test_turning_it_on_sends_the_page_and_shows_it(self, editor, plate):
        # WHEN
        self._start(editor, plate)

        # THEN
        calls = plate.calls
        assert calls[0] == ("clear_page", 9)
        assert {(9, 1), (9, 2)} <= set(_sent_objects(plate))
        assert calls[-1] == ("set_page", 9)

    def test_an_edit_sends_only_the_changed_property(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.set_source_value(_object(editor, 1), "x", 20)
        editor._mark_dirty()

        # THEN
        _wait_until(lambda: plate.calls)
        assert plate.calls == [("jsonl", {"page": 9, "id": 1, "x": 20})]

    def test_fast_edits_are_coalesced_and_the_last_one_is_sent(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()
        label = _object(editor, 1)

        # WHEN
        for x in range(20, 30):
            editor.session.set_source_value(label, "x", x)
            editor._mark_dirty()

        # THEN
        _wait_until(lambda: plate.calls and plate.calls[-1] == ("jsonl", {"page": 9, "id": 1, "x": 29}))
        assert len(plate.calls) == 2

    def test_removing_an_object_deletes_it(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.remove_object(_object(editor, 2))
        editor._mark_dirty()

        # THEN
        _wait_until(lambda: plate.calls)
        assert plate.calls == [("delete_object_id", 9, 2)]

    def test_clear_page_is_disabled_while_it_is_on(self, editor, plate):
        # WHEN
        self._start(editor, plate)

        # THEN
        assert editor.action_clear.isEnabled() is False

    def test_stopping_silently_sends_nothing_more(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.stop_live_preview()
        editor.session.set_source_value(_object(editor, 1), "x", 20)
        editor._mark_dirty()

        # THEN
        from PyQt6.QtTest import QTest

        QTest.qWait(150)
        assert plate.calls == []
        assert editor.live_preview is False


class TestRestorePlate(TestBase):
    def test_restore_ends_live_preview_and_rebuilds_the_plate_from_its_files(self, editor, plate):
        # GIVEN
        restored = []
        editor.plateRestored.connect(lambda: restored.append(True))
        editor.action_live_preview.setChecked(True)
        _wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        plate.clear()

        # WHEN
        editor.restore_plate()

        # THEN
        _wait_until(lambda: restored)
        assert plate.calls == [("restore_from_files",)]
        assert editor.live_preview is False


def _key(editor, file_name: str) -> str:
    return next(component.key for component in editor.session.components if component.path.name == file_name)


class TestFiles(TestBase):
    def test_new_objects_go_to_the_chosen_file(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)

        # WHEN
        editor.add_object(OpenHASPWidgetType.LABEL)

        # THEN
        added = editor.working_objects[home][-1]
        assert (added["page"], added["obj"]) == (9, "label")
        assert editor.target_component == home

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
