"""The page layout editor of a device, and a plate that records what the editor sends to it."""


import pytest

from openhasp_config_manager.gui.domain.draft.files import load_device
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests.helpers import DEVICE_DIR, copy_test_config, create_config_manager
from tests.gui.page_layout_editor.helpers import EDITOR_JSONL, _Plate


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
def boot_cmd():
    """:return: the startup script of the device (classes override it)"""
    return "run L:/home_page.jsonl\nrun L:/editor.jsonl\n"


@pytest.fixture
def editor(qapp, async_loop, plate, tmp_path, monkeypatch, editor_files, boot_cmd):
    from openhasp_config_manager.gui.qt.operations import OperationStatus
    from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData, plate_link
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget

    monkeypatch.setattr(plate_link, "SEND_DELAY_SECONDS", 0)

    root = copy_test_config(tmp_path, {**editor_files, f"{DEVICE_DIR}/boot.cmd": boot_cmd})
    loaded = load_device(create_config_manager(root), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)

    widget = PageLayoutEditorWidget(status=OperationStatus())
    widget.set_data(
        session=session,
        device_pages_data=OpenHaspDevicePagesData(
            device=loaded.device,
            name=loaded.cmd_component.name,
            jsonl_components=loaded.jsonl_components,
            part_includers=loaded.part_includers,
        ),
        page=9,
    )
    return widget
