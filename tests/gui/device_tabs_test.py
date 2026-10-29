import shutil
from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.helpers import EDITOR_JSONL, create_editor_cfg_root, gui_state, wait_until
from tests.helpers import DEVICE_DIR

SECOND_DEVICE = "second_device"


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    """The editor config, with a copy of its device as a second one."""
    root = create_editor_cfg_root(tmp_path)
    shutil.copytree(root / DEVICE_DIR, root / "devices" / SECOND_DEVICE)
    (root / "devices" / SECOND_DEVICE / "editor.jsonl").write_text(EDITOR_JSONL.replace('"page": 9', '"page": 3'))
    return root


def _open(window, name: str):
    window.on_device_selected(name)
    wait_until(lambda: window.device is not None and window.device.name == name and window.session is not None)


def _label(window):
    [component] = window.session.components
    return window.session.working_objects[component.key][0]


class TestDeviceTabs(TestBase):
    def test_opening_a_second_device_keeps_the_first_tab_with_its_page_and_zoom(self, window):
        # GIVEN
        first = window.page_layout_editor_widget
        first.set_page_index(9)
        first.page_preview_widget.set_zoom(1.7)

        # WHEN
        _open(window, SECOND_DEVICE)

        # THEN
        assert [tab.name for tab in window.device_tabs.tabs] == ["test_device", SECOND_DEVICE]
        assert window.page_layout_editor_widget is not first
        assert window.page_layout_editor_widget.current_index == 3
        assert first.current_index == 9
        assert first.page_preview_widget.zoom() == pytest.approx(1.7)
        assert first.session is window.sessions[window.device_tabs.find("test_device").session_key]

    def test_switching_back_does_not_load_the_device_again(self, window, monkeypatch):
        # GIVEN
        from openhasp_config_manager.gui.qt.window import main as window_module

        first = window.page_layout_editor_widget
        first.set_page_index(9)
        session = window.session
        _open(window, SECOND_DEVICE)
        loads = []
        monkeypatch.setattr(window_module, "load_device", lambda *args: loads.append(args))

        # WHEN
        window.on_device_selected("test_device")

        # THEN
        assert window.device.name == "test_device"
        assert window.page_layout_editor_widget is first
        assert window.session is session
        assert first.current_index == 9
        assert window.center_stack.currentWidget() is first
        assert loads == []

    def test_the_panels_follow_the_active_tab(self, window, cfg_root):
        # GIVEN
        first = window.page_layout_editor_widget
        _open(window, SECOND_DEVICE)
        second = window.page_layout_editor_widget

        # WHEN
        window.device_tabs.activate(window.device_tabs.find("test_device"))

        # THEN
        assert window.properties_stack.currentWidget() is first.property_editor
        assert window.page_jsonl_stack.currentWidget() is first.jsonl_preview
        assert window.connection._device_name == "test_device"
        assert window.ui_session.session.selected_device == "test_device"
        wait_until(lambda: (gui_state(cfg_root).get("device") or {}).get("name") == "test_device")

        # WHEN
        window.device_tabs.activate(window.device_tabs.find(SECOND_DEVICE))

        # THEN
        assert window.properties_stack.currentWidget() is second.property_editor
        assert window.connection._device_name == SECOND_DEVICE
        wait_until(lambda: (gui_state(cfg_root).get("device") or {}).get("name") == SECOND_DEVICE)

    def test_a_closed_tab_keeps_its_draft(self, window):
        # GIVEN
        _open(window, SECOND_DEVICE)
        window.session.set_source_value(_label(window), "x", 42)
        tab = window.device_tabs.active

        # WHEN
        assert window.close_tab(tab)

        # THEN
        assert [tab.name for tab in window.device_tabs.tabs] == ["test_device"]
        assert window.device.name == "test_device"
        assert window.sessions[tab.session_key].is_dirty

        # WHEN
        _open(window, SECOND_DEVICE)

        # THEN
        assert _label(window)["x"] == 42

    def test_closing_the_last_tab_shows_that_no_device_is_selected(self, window):
        # WHEN
        window.close_tab(window.device_tabs.active)

        # THEN
        assert window.device_tabs.tabs == []
        assert window.device is None
        assert window.session is None
        assert window.center_stack.currentWidget() is window.message_panel

        # WHEN
        _open(window, "test_device")

        # THEN
        assert window.center_stack.currentWidget() is window.page_layout_editor_widget

    def test_the_title_of_a_tab_marks_unsaved_changes(self, window):
        # GIVEN
        tab = window.device_tabs.active
        assert window.device_tabs.title(tab) == "test_device"

        # WHEN
        window.session.set_source_value(_label(window), "x", 42)

        # THEN
        assert window.device_tabs.title(tab) == "test_device •"

        # WHEN: another tab is active, and the draft is saved
        _open(window, SECOND_DEVICE)
        window.device_tabs.activate(tab)
        assert window.draft_actions.save()

        # THEN
        assert window.device_tabs.title(tab) == "test_device"

    def test_undo_undoes_in_the_draft_of_the_active_tab(self, window):
        # GIVEN: both editors have their Undo with the same shortcut
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        window.show()
        window.activateWindow()
        wait_until(lambda: window.isActiveWindow())
        window.session.set_source_value(_label(window), "x", 41)
        first = window.session
        _open(window, SECOND_DEVICE)
        window.session.set_source_value(_label(window), "x", 42)
        window.page_layout_editor_widget.page_preview_widget.setFocus()

        # WHEN
        QTest.keyClick(window.page_layout_editor_widget.page_preview_widget, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

        # THEN
        wait_until(lambda: _label(window)["x"] == 10)
        assert first.undo_description is not None
