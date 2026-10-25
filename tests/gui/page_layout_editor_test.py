import math
import shutil
import threading
from pathlib import Path

import orjson
import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft_files import load_device
from openhasp_config_manager.gui.domain.plate_session import PlateSession
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


def _sent_objects(plate: _Plate):
    return [(call[1].get("page"), call[1].get("id")) for call in plate.calls if call[0] == "jsonl"]


def _object(editor, obj_id: int):
    return next(obj for obj in editor.page_objects if obj.get("page") == 9 and obj.get("id") == obj_id)


class TestLivePreview(TestBase):
    def _start(self, editor, plate):
        editor.action_live_preview.setChecked(True)
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
        editor._mark_dirty()

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
            editor._mark_dirty()

        # THEN
        wait_until(lambda: plate.calls and plate.calls[-1] == ("jsonl", {"page": 9, "id": 1, "x": 29}))
        assert len(plate.calls) == 2

    def test_removing_an_object_deletes_it(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.remove_object(_object(editor, 2))
        editor._mark_dirty()

        # THEN
        wait_until(lambda: plate.calls)
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
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        plate.clear()

        # WHEN
        editor.restore_plate()

        # THEN
        wait_until(lambda: restored)
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

    def test_a_new_tab_goes_into_the_tabview_of_the_page(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)
        editor.add_object(OpenHASPWidgetType.TABVIEW)
        tabview = editor.working_objects[home][-1]

        # WHEN
        editor.add_object(OpenHASPWidgetType.TAB)

        # THEN
        assert editor.working_objects[home][-1]["parentid"] == tabview["id"]

    def test_a_tab_needs_a_tabview_on_the_page(self, editor):
        # GIVEN
        from openhasp_config_manager.gui.domain.page_objects import OpenHASPWidgetType

        home = _key(editor, "page.jsonl")
        editor.set_target_component(home)
        count = len(editor.working_objects[home])

        # WHEN
        editor.add_object(OpenHASPWidgetType.TAB)

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
        editor.remove_selected_objects()

        # THEN
        assert len(rebuilds) == 1
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
        editor.nudge_selected_objects(1, 0)
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


class TestHighlightComponent(TestBase):
    def _dimmed_ids(self, editor):
        return [orjson.loads(selection.cursor.block().text())["id"] for selection in editor.jsonl_preview.extraSelections()]

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
