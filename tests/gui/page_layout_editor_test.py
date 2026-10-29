import math
import shutil
import threading
from pathlib import Path

import orjson
import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft.files import load_device
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests import TestBase
from tests.gui.helpers import wait_until

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
def editor_files():
    """:return: the files the test writes into the config directory: path -> content (classes override it)"""
    return {"devices/test_device/editor.jsonl": EDITOR_JSONL}


@pytest.fixture
def editor(qapp, async_loop, plate, tmp_path, monkeypatch, editor_files):
    from openhasp_config_manager.gui.qt.operations import OperationStatus
    from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData, plate_link
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget

    monkeypatch.setattr(plate_link, "SEND_DELAY_SECONDS", 0)

    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device_dir = root / "devices" / "test_device"
    for name, content in editor_files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
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


def _sent_objects(plate: _Plate):
    return [(call[1].get("page"), call[1].get("id")) for call in plate.calls if call[0] == "jsonl"]


def _object(editor, obj_id: int):
    return next(obj for obj in editor.page_objects if obj.get("page") == 9 and obj.get("id") == obj_id)


class TestLivePreview(TestBase):
    def _start(self, editor, plate):
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))

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

        # THEN
        wait_until(lambda: plate.calls)
        assert plate.calls == [("jsonl", {"page": 9, "id": 1, "x": 20})]

    def test_fast_edits_are_coalesced_and_the_last_one_is_sent(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()
        label = _object(editor, 1)

        # WHEN
        for x in range(20, 30):
            editor.session.set_source_value(label, "x", x)

        # THEN
        wait_until(lambda: plate.calls and plate.calls[-1] == ("jsonl", {"page": 9, "id": 1, "x": 29}))
        assert len(plate.calls) == 2

    def test_removing_an_object_deletes_it(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.remove_object(_object(editor, 2))

        # THEN
        wait_until(lambda: plate.calls)
        assert plate.calls == [("delete_object_id", 9, 2)]

    def _go_to(self, editor, plate, index: int):
        editor._go_to_page(index)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", index))

    def test_a_page_that_was_sent_before_is_only_shown(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        assert ("clear_page", 1) in plate.calls
        plate.clear()

        # WHEN
        self._go_to(editor, plate, 9)

        # THEN
        assert plate.calls == [("set_page", 9)]

    def test_changes_of_a_page_that_is_not_shown_are_sent_when_it_is(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        self._go_to(editor, plate, 9)
        plate.clear()

        # WHEN
        label = next(obj for obj in editor.session.working_objects[_key(editor, "editor.jsonl")] if obj.get("id") == 50)
        editor.session.set_source_value(label, "x", 7)
        self._go_to(editor, plate, 1)

        # THEN
        assert plate.calls == [("jsonl", {"page": 1, "id": 50, "x": 7}), ("set_page", 1)]

    def test_objects_removed_from_a_page_that_is_not_shown_are_deleted_when_it_is(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        self._go_to(editor, plate, 9)
        plate.clear()

        # WHEN
        label = next(obj for obj in editor.session.working_objects[_key(editor, "editor.jsonl")] if obj.get("id") == 50)
        editor.session.remove_object(label)
        self._go_to(editor, plate, 1)

        # THEN
        assert plate.calls == [("delete_object_id", 1, 50), ("set_page", 1)]

    def test_a_page_the_editor_left_before_it_was_sent_is_not_sent(self, editor, plate, monkeypatch):
        # GIVEN: sending the first page takes a while
        from openhasp_config_manager.gui.qt.widgets.pagelayout import plate_link

        monkeypatch.setattr(plate_link, "SEND_DELAY_SECONDS", 0.05)
        editor.plate.action_live_preview.setChecked(True)

        # WHEN
        editor._go_to_page(1)
        editor._go_to_page(9)

        # THEN: page 9 was sent once, and is shown again
        wait_until(lambda: plate.calls.count(("set_page", 9)) == 2)
        assert ("clear_page", 1) not in plate.calls
        assert plate.calls.count(("clear_page", 9)) == 1

    def test_forgotten_pages_are_sent_in_full_again(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        plate.clear()

        # WHEN: e.g. the plate restarted
        editor.plate.forget_sent()
        self._go_to(editor, plate, 9)

        # THEN
        assert plate.calls[0] == ("clear_page", 9)

    def test_clear_page_is_disabled_while_it_is_on(self, editor, plate):
        # WHEN
        self._start(editor, plate)

        # THEN
        assert editor.plate.action_clear.isEnabled() is False

    def test_stopping_silently_sends_nothing_more(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.plate.stop_live_preview()
        editor.session.set_source_value(_object(editor, 1), "x", 20)

        # THEN
        from PyQt6.QtTest import QTest

        QTest.qWait(150)
        assert plate.calls == []
        assert editor.plate.live is False


class TestRestorePlate(TestBase):
    def test_restore_ends_live_preview_and_rebuilds_the_plate_from_its_files(self, editor, plate):
        # GIVEN
        restored = []
        editor.plate.plateRestored.connect(lambda: restored.append(True))
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        plate.clear()

        # WHEN
        editor.plate.restore_plate()

        # THEN
        wait_until(lambda: restored)
        assert plate.calls == [("restore_from_files",)]
        assert editor.plate.live is False


def _key(editor, file_name: str) -> str:
    return next(component.key for component in editor.session.components if component.path.name == file_name)


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


class TestIncludedObjects(TestBase):
    @pytest.fixture
    def editor_files(self):
        return {
            "common/parts/dot.jsonl": '{"page": 9, "id": "{{ id }}", "obj": "label", "x": "{{ id * 10 }}", "text": "{{ id }}"}\n',
            "devices/test_device/editor.jsonl": EDITOR_JSONL
            + '{"!include": "common/parts/dot.jsonl", "for": {"id": [20, 21]}}\n',
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
        assert editor.property_editor.findChildren(QLineEdit) == []
        texts = [label.text() for label in editor.property_editor.findChildren(QLabel)]
        assert "common/parts/dot.jsonl:1  ·  included" in texts
        assert "210" in texts


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
