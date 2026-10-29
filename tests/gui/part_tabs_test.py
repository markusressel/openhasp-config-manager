"""Part tabs: "Edit the part" opens a tab with one instance of a part of a device, its objects alone or on their page."""

import threading
from pathlib import Path
from typing import List

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, TEST_CFG_ROOT, TEST_DEVICE, copy_test_config

OTHER_DEVICE = "other_device"

# a shared part, two objects per instance
TILE_JSONL = (
    '{"page": 1, "id": "{{ id }}", "obj": "btn", "x": "{{ id * 4 }}", "y": 120, "w": 60, "h": 60, "text": "{{ id }}"}\n'
    '{"page": 1, "id": "{{ id + 1 }}", "obj": "label", "x": "{{ id * 4 }}", "y": 190, "text": "-"}\n'
)

PAGE_JSONL = (
    '{"page": 1, "id": 1, "obj": "label", "x": 10, "y": 10, "text": "Title"}\n'
    '{"!include": "common/parts/tile.jsonl", "for": {"id": [20, 30]}}\n'
)

# another file of the test device, outside of the part tabs
OTHER_JSONL = '{"page": 2, "id": 5, "obj": "label", "x": 10, "text": "Other"}\n'

OTHER_DEVICE_JSONL = '{"!include": "common/parts/tile.jsonl", "for": {"id": [40]}}\n'

# no page includes it
CARD_JSONL = '{"page": 3, "id": 7, "obj": "label", "x": 5, "text": "card"}\n'


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    pytest.importorskip("watchdog")
    config = (TEST_CFG_ROOT / DEVICE_DIR / "config.json").read_text()
    return copy_test_config(
        tmp_path,
        {
            "common/parts/tile.jsonl": TILE_JSONL,
            f"{DEVICE_DIR}/page.jsonl": PAGE_JSONL,
            f"{DEVICE_DIR}/other.jsonl": OTHER_JSONL,
            f"{DEVICE_DIR}/card.jsonl": CARD_JSONL,
            f"{DEVICE_DIR}/boot.cmd": "run L:/page.jsonl\nrun L:/other.jsonl\n",
            f"devices/{OTHER_DEVICE}/config.json": config,
            f"devices/{OTHER_DEVICE}/page.jsonl": OTHER_DEVICE_JSONL,
            f"devices/{OTHER_DEVICE}/boot.cmd": "run L:/page.jsonl\n",
        },
    )


class _Plates:
    """What is sent to the plates (from the background loop): (device, call)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: List[tuple] = []

    def record(self, *call):
        with self._lock:
            self._calls.append(call)

    def calls(self, device: str) -> List[tuple]:
        with self._lock:
            return [call[1:] for call in self._calls if call[0] == device]


@pytest.fixture
def plates(monkeypatch) -> _Plates:
    from openhasp_config_manager.gui.qt.widgets.pagelayout import plate_link
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    plates = _Plates()

    def recording(name):
        async def method(client, *args):
            plates.record(client._device.name, name, *args)

        return method

    for name in ["clear_page", "jsonl", "set_page", "delete_object_id", "restore_from_files"]:
        monkeypatch.setattr(OpenHaspClient, name, recording(name))
    monkeypatch.setattr(plate_link, "SEND_DELAY_SECONDS", 0)
    return plates


@pytest.fixture
def tile(cfg_root) -> Path:
    return (cfg_root / "common" / "parts" / "tile.jsonl").resolve()


def _open(window, name: str):
    window.on_device_selected(name)
    wait_until(lambda: window.device is not None and window.device.name == name and window.session is not None)


def _object(session, obj_id: int):
    return next(obj for objects in session.working_objects.values() for obj in objects if obj.get("id") == obj_id)


def _shown(editor) -> List[int]:
    return sorted(item.obj_data.get("id") for item in editor.page_preview_widget.editable_items() if item.isVisible())


class TestPartTabs(TestBase):
    def test_edit_the_part_opens_a_part_tab_which_is_focused_when_asked_for_again(self, window, tile):
        from openhasp_config_manager.gui.qt.window.device_tabs import PartTab

        # GIVEN
        pages = window.device_tabs.active
        session = window.session
        first, second = session.part_instances(tile)

        # WHEN
        window.edit_part(tile)

        # THEN: a tab of its own, on the first instance, with only its objects shown
        tab = window.device_tabs.active
        assert isinstance(tab, PartTab) and window.device_tabs.tabs == [pages, tab]
        assert window.device_tabs.title(tab) == "tile.jsonl · test_device"
        editor = window.page_layout_editor_widget
        assert editor is tab.editor is not pages.editor
        assert editor.session is session and editor.part_mode == first and editor.edit_mode
        assert _shown(editor) == [20, 21]
        assert pages.editor.part_mode is None and _shown(pages.editor) == [1, 20, 21, 30, 31]

        # WHEN: from the pages again, for the other instance
        window.device_tabs.activate(pages)
        window.edit_part(tile, second, session)

        # THEN: the same tab, on that instance
        assert window.device_tabs.active is tab and len(window.device_tabs.tabs) == 2
        assert editor.part_mode == second and _shown(editor) == [30, 31]

        # WHEN
        focus = tab.focus
        editor.part_bar.done.click()

        # THEN
        assert window.device_tabs.tabs == [pages] and window.device_tabs.active is pages
        assert focus.instance is None

    def test_the_same_part_on_two_devices_and_an_edit_of_it_in_both(self, window, tile):
        # GIVEN: a part tab of each device
        window.edit_part(tile)
        first = window.device_tabs.active
        _open(window, OTHER_DEVICE)
        window.edit_part(tile)
        second = window.device_tabs.active

        # WHEN
        first.editor.editing.set_source_value(_object(first.focus.session, 20), "text", "#{{ id }}")

        # THEN: the shared part changes in the other device too, and both tabs show unsaved changes
        assert [tab.title for tab in window.device_tabs.tabs] == [
            "test_device",
            "tile.jsonl · test_device",
            OTHER_DEVICE,
            f"tile.jsonl · {OTHER_DEVICE}",
        ]
        assert _object(second.focus.session, 40)["text"] == "#40"
        assert first.dirty and second.dirty
        assert window.device_tabs.title(second) == f"tile.jsonl · {OTHER_DEVICE} •"

    def test_undo_and_the_mark_of_unsaved_changes_are_about_the_part_and_its_file(self, window, tile):
        # GIVEN: an edit of the other file of the device, then one of the part in its tab
        pages = window.device_tabs.active
        session = window.session
        session.set_source_value(_object(session, 5), "x", 11)
        window.edit_part(tile)
        tab = window.device_tabs.active
        editor = tab.editor

        # THEN: the part tab has nothing to undo and no unsaved changes
        assert pages.dirty and not tab.dirty
        assert not editor.action_undo.isEnabled()

        # WHEN
        editor.editing.set_source_value(_object(session, 20), "y", 130)

        # THEN
        assert tab.dirty
        assert editor.action_undo.text() == "Undo Change y of p1b20"

        # WHEN: undone in the part tab
        editor.action_undo.trigger()

        # THEN: only the edit of the part, the other file keeps its change
        assert _object(session, 20)["y"] == 120 and _object(session, 5)["x"] == 11
        assert not tab.dirty and not editor.action_undo.isEnabled()
        assert pages.editor.action_undo.text() == "Undo Change x of p2b5"

    def test_a_part_that_no_page_includes_is_a_part_tab_of_its_own(self, window, cfg_root):
        # GIVEN
        pages = window.device_tabs.active
        card = (cfg_root / DEVICE_DIR / "card.jsonl").resolve()

        # WHEN
        window.file_tree_widget.editPartRequested.emit(card)

        # THEN: the pages of the device stay in their tab
        tab = window.device_tabs.active
        assert tab.alone and tab is not pages
        assert [obj.get("id") for obj in tab.editor.page_objects] == [7]
        assert pages.editor.session is window.sessions[pages.session_key]
        assert window.session is tab.focus.session is not pages.editor.session

    def test_a_revert_goes_on_in_the_instance_and_a_part_that_is_not_included_anymore_closes_its_tab(self, window, tile, cfg_root):
        # GIVEN
        session = window.session
        window.edit_part(tile, session.part_instances(tile)[1], session)
        tab = window.device_tabs.active
        tab.editor.editing.set_source_value(_object(session, 30), "y", 130)

        # WHEN
        window.reload_draft()

        # THEN
        wait_until(lambda: tab.device is not None and window.session is not None and window.session is not session)
        assert tab in window.device_tabs.tabs
        assert window.session.describe_instance(tab.focus.instance) == "devices/test_device/page.jsonl:2 (id=30)"
        assert tab.editor.part_mode == tab.focus.instance and _shown(tab.editor) == [30, 31]
        assert _object(window.session, 30)["y"] == 120

        # WHEN: the page doesn't include it anymore
        (cfg_root / DEVICE_DIR / "page.jsonl").write_text(PAGE_JSONL.splitlines()[0] + "\n")

        # THEN
        wait_until(lambda: tab not in window.device_tabs.tabs)
        assert [tab.title for tab in window.device_tabs.tabs] == ["test_device"]

    def test_live_preview_of_the_device_sends_the_page_of_the_tab_that_was_active_last(self, window, tile, plates):
        # GIVEN: Live preview in the tab of the pages, on page 2
        pages = window.device_tabs.active
        pages.editor._go_to_page(2)
        pages.editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plates.calls(TEST_DEVICE)[-1:] == [("set_page", 2)])

        # WHEN
        window.edit_part(tile)
        tab = window.device_tabs.active

        # THEN: one Live preview for the device, which shows the page of the part
        assert tab.editor.plate is pages.editor.plate and tab.editor.plate.live
        wait_until(lambda: plates.calls(TEST_DEVICE)[-1:] == [("set_page", 1)])

        # WHEN: an edit in the part tab
        tab.editor.editing.set_source_value(_object(window.session, 20), "y", 130)

        # THEN
        wait_until(lambda: ("jsonl", {"page": 1, "id": 20, "y": 130}) in plates.calls(TEST_DEVICE))

        # WHEN
        window.close_tab(tab)

        # THEN: Live preview goes on with the page of the tab of the pages
        assert pages.editor.plate.live
        wait_until(lambda: plates.calls(TEST_DEVICE)[-1:] == [("set_page", 2)])

    def test_the_bar_of_a_part_tab_stays_one_line_in_a_small_window(self, window, tile):
        # GIVEN
        window.show()
        window.resize(900, 600)

        # WHEN
        window.edit_part(tile)

        # THEN: the editor fits next to the docks, and the bar is one row with all of its buttons
        editor = window.page_layout_editor_widget
        wait_until(lambda: editor.mapTo(window, editor.rect().topRight()).x() < window.properties_dock.x())
        bar = editor.part_bar
        assert bar.height() < 2 * bar.done.sizeHint().height()
        assert bar.done.geometry().right() <= bar.width()
        assert editor.widget_picker.is_compact
