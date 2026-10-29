"""The connections and Live preview of the open devices: one per device, also while its tab is in the background."""

import asyncio
import threading
from pathlib import Path
from typing import Dict, List

import pytest

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, TEST_CFG_ROOT, TEST_DEVICE, copy_test_config

OTHER_DEVICE = "other_device"

BOOT_CMD = "run L:/common_shared.jsonl\nrun L:/page.jsonl\n"

# both devices run it
SHARED_JSONL = '{"page": 2, "id": 1, "obj": "label", "x": 10, "text": "shared"}\n'

PAGE_JSONL = '{"page": 9, "id": 1, "obj": "label", "x": 1, "text": "own"}\n'


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    config = (TEST_CFG_ROOT / DEVICE_DIR / "config.json").read_text()
    files = {"common/shared.jsonl": SHARED_JSONL}
    for device in [TEST_DEVICE, OTHER_DEVICE]:
        files.update(
            {
                f"devices/{device}/config.json": config,
                f"devices/{device}/boot.cmd": BOOT_CMD,
                f"devices/{device}/page.jsonl": PAGE_JSONL,
            }
        )
    return copy_test_config(tmp_path, files)


class _Broker:
    """The MQTT connections of the window: what they listen to, and the events the test sends to them."""

    def __init__(self):
        self.clients: List["_Client"] = []

    def client(self, device: str) -> "_Client":
        """:return: the connection of a device that is still open"""
        [client] = [client for client in self.clients if client.device == device and not client.closed]
        return client

    def report(self, device: str, path: str, payload: str):
        """A message of the plate of a device, e.g. its LWT."""
        wait_until(lambda: path in self.client(device).callbacks)
        asyncio.run(self.client(device).callbacks[path]("", payload.encode("utf-8")))


class _Client:
    def __init__(self, broker: _Broker, device):
        self.device = device.name
        self.listeners = []
        self.callbacks: Dict[str, object] = {}
        self.cancelled = 0
        broker.clients.append(self)

    @property
    def closed(self) -> bool:
        return not self.listeners and self.cancelled == 2

    def add_connection_listener(self, listener):
        self.listeners.append(listener)

    def remove_connection_listener(self, listener):
        self.listeners.remove(listener)

    async def listen_event(self, path, callback):
        self.callbacks[path] = callback

    async def cancel_callback(self, callback):
        self.cancelled += 1


class _Plates:
    """What is sent to the plates, per device (from the background loop)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: Dict[str, List[tuple]] = {}

    def record(self, device: str, *call):
        with self._lock:
            self._calls.setdefault(device, []).append(call)

    def calls(self, device: str) -> List[tuple]:
        with self._lock:
            return list(self._calls.get(device, []))

    def clear(self):
        with self._lock:
            self._calls.clear()


@pytest.fixture
def broker(create_window, monkeypatch) -> _Broker:
    from openhasp_config_manager.gui.qt import connection

    broker = _Broker()
    monkeypatch.setattr(connection, "OpenHaspClient", lambda device: _Client(broker, device))
    return broker


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
def window(create_window, broker, plates):
    """A window with both devices open, the other one in the active tab."""
    window = create_window()
    wait_until(lambda: window.devices)
    for name in [TEST_DEVICE, OTHER_DEVICE]:
        _open(window, name)
    return window


def _open(window, name: str):
    window.on_device_selected(name)
    wait_until(lambda: window.device is not None and window.device.name == name and window.session is not None)


def _tab(window, name: str):
    return window.device_tabs.find(name)


def _object(window, name: str, page: int):
    session = window.sessions[_tab(window, name).session_key]
    return next(obj for objects in session.working_objects.values() for obj in objects if obj.get("page") == page)


def _start_live_preview(window, plates: _Plates, name: str, page: int):
    tab = _tab(window, name)
    tab.editor.set_page_index(page)
    tab.editor.plate.action_live_preview.setChecked(True)
    wait_until(lambda: plates.calls(name) and plates.calls(name)[-1] == ("set_page", page))


class TestConnections(TestBase):
    def test_both_devices_are_connected_at_once(self, window, broker):
        # WHEN
        for name in [TEST_DEVICE, OTHER_DEVICE]:
            broker.client(name).listeners[0](True, None)
        broker.report(TEST_DEVICE, "LWT", "online")
        broker.report(OTHER_DEVICE, "state/page", "3")

        # THEN
        from openhasp_config_manager.gui.domain.connection import LinkState

        wait_until(lambda: window.connections.get(TEST_DEVICE).status.link == LinkState.PLATE_ONLINE)
        wait_until(lambda: window.connections.get(OTHER_DEVICE).status.link == LinkState.PLATE_UNKNOWN)
        assert window.connections.get(OTHER_DEVICE).status.page == 3
        # the status bar shows the active tab's device
        assert window.connection is window.connections.get(OTHER_DEVICE)
        assert window.status_bar._connection.text() == "No status from plate"
        assert "The plate is connected" in window.device_tabs.bar.tabToolTip(0)

        # WHEN
        window.device_tabs.activate(_tab(window, TEST_DEVICE))

        # THEN
        assert window.status_bar._connection.text() == "Online"

    def test_closing_a_tab_closes_its_connection(self, window, broker):
        # GIVEN
        client = broker.client(OTHER_DEVICE)

        # WHEN
        assert window.close_tab(_tab(window, OTHER_DEVICE))

        # THEN
        wait_until(lambda: client.closed)
        assert window.connections.names == [TEST_DEVICE]
        assert not broker.client(TEST_DEVICE).closed
        assert [row.device for row in window.plates_panel.rows] == [TEST_DEVICE]


class TestLivePreviewPerDevice(TestBase):
    def test_live_preview_keeps_running_in_a_background_tab(self, window, plates):
        # GIVEN
        _start_live_preview(window, plates, OTHER_DEVICE, 9)
        window.device_tabs.activate(_tab(window, TEST_DEVICE))
        plates.clear()

        # WHEN
        window.sessions[_tab(window, OTHER_DEVICE).session_key].set_source_value(_object(window, OTHER_DEVICE, 9), "x", 20)

        # THEN
        assert _tab(window, OTHER_DEVICE).editor.plate.live
        wait_until(lambda: plates.calls(OTHER_DEVICE) == [("jsonl", {"page": 9, "id": 1, "x": 20})])
        assert plates.calls(TEST_DEVICE) == []

    def test_an_edit_of_a_shared_file_in_one_tab_is_sent_to_the_plate_of_the_other(self, window, plates):
        # GIVEN: Live preview on the other device, in the background
        _start_live_preview(window, plates, OTHER_DEVICE, 2)
        window.device_tabs.activate(_tab(window, TEST_DEVICE))
        plates.clear()

        # WHEN: the shared file is edited in the tab of the test device
        window.session.set_source_value(_object(window, TEST_DEVICE, 2), "x", 30)

        # THEN
        wait_until(lambda: plates.calls(OTHER_DEVICE) == [("jsonl", {"page": 2, "id": 1, "x": 30})])
        assert plates.calls(TEST_DEVICE) == []

    def test_live_preview_is_refused_beyond_the_limit_and_names_the_others(self, window, plates, monkeypatch):
        # GIVEN: a limit of one device, which has Live preview on
        from PyQt6.QtWidgets import QMessageBox

        from openhasp_config_manager.gui.domain import live_preview

        monkeypatch.setattr(live_preview, "MAX_LIVE_PREVIEWS", 1)
        messages = []
        monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append(text))
        _start_live_preview(window, plates, OTHER_DEVICE, 9)

        # WHEN
        window.set_live_preview(TEST_DEVICE, True)

        # THEN
        assert not _tab(window, TEST_DEVICE).editor.plate.live
        assert _tab(window, OTHER_DEVICE).editor.plate.live
        [message] = messages
        assert OTHER_DEVICE in message
        assert plates.calls(TEST_DEVICE) == []


class TestPlatesPanel(TestBase):
    def test_a_row_per_open_device(self, window, broker, plates):
        # GIVEN
        broker.client(TEST_DEVICE).listeners[0](False, ConnectionRefusedError("refused"))

        # WHEN
        window.set_live_preview(OTHER_DEVICE, True)
        wait_until(lambda: plates.calls(OTHER_DEVICE))
        window.connections.get(OTHER_DEVICE).page_out_of_sync(4)

        # THEN
        wait_until(lambda: len(window.plates_panel.rows) == 2 and window.plates_panel.rows[0].connection.error is not None)
        tree = window.plates_panel.tree
        rows = [[tree.topLevelItem(row).text(column) for column in range(5)] for row in range(tree.topLevelItemCount())]
        assert rows[0][:2] == [TEST_DEVICE, "Broker unreachable"]
        assert "refused" in rows[0][4]
        assert rows[1][0] == OTHER_DEVICE
        assert rows[1][4] == "Out of sync: page 4"
        assert [row.live for row in window.plates_panel.rows] == [False, True]

    def test_a_click_focuses_the_tab_of_the_device(self, window):
        # WHEN
        tree = window.plates_panel.tree
        tree.itemClicked.emit(tree.topLevelItem(0), 0)

        # THEN
        assert window.device.name == TEST_DEVICE
