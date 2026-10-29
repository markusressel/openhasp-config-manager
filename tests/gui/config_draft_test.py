from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from openhasp_config_manager.gui.domain.draft.config_draft import ConfigDraft
from openhasp_config_manager.gui.domain.draft.files import plan_save, write_save
from openhasp_config_manager.gui.domain.draft.model import ChangeKind, DraftChange
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import object_name
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, TEST_CFG_ROOT, copy_test_config, load_session

OTHER_DEVICE = "other_device"

BOOT_CMD = "run L:/common_shared.jsonl\nrun L:/page.jsonl\n"

# a page file of the common folder: both devices run it, each renders the variable with its own value
SHARED_JSONL = """{"page": 2, "id": 1, "obj": "label", "text": "{{ key_also_present_in_device_vars }}"}
{"page": 2, "id": 2, "obj": "label", "text": "two"}
"""

TILE_JSONL = '{"page": "{{ page }}", "id": "{{ id }}", "obj": "label", "x": 5, "text": "tile"}\n'

# the own page of each device (the same content, in two files), with an instance of the shared part
PAGE_JSONL = """{"page": 9, "id": 1, "obj": "obj", "x": 1}
{"!include": "common/parts/tile.jsonl", "vars": {"page": 9, "id": 20}}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    config = (TEST_CFG_ROOT / DEVICE_DIR / "config.json").read_text()
    return copy_test_config(
        tmp_path,
        {
            "common/shared.jsonl": SHARED_JSONL,
            "common/parts/tile.jsonl": TILE_JSONL,
            f"{DEVICE_DIR}/boot.cmd": BOOT_CMD,
            f"{DEVICE_DIR}/page.jsonl": PAGE_JSONL,
            f"devices/{OTHER_DEVICE}/config.json": config,
            f"devices/{OTHER_DEVICE}/boot.cmd": BOOT_CMD,
            f"devices/{OTHER_DEVICE}/page.jsonl": PAGE_JSONL,
        },
    )


@pytest.fixture
def config() -> ConfigDraft:
    return ConfigDraft()


@pytest.fixture
def devices(cfg_root, config) -> Tuple[PlateSession, PlateSession]:
    """The drafts of the two devices, on one `ConfigDraft`."""
    return load_session(cfg_root, config=config), load_session(cfg_root, OTHER_DEVICE, config)


def _objects(session: PlateSession) -> Dict[str, Dict]:
    return {object_name(obj): obj for objects in session.working_objects.values() for obj in objects}


def _listened(session: PlateSession) -> List[DraftChange]:
    changes = []
    session.add_listener(changes.append)
    return changes


class TestSharedFiles:
    def test_each_device_renders_a_shared_file_with_its_variables(self, devices):
        # GIVEN
        device, other = devices

        # THEN
        assert _objects(device)["p2b1"]["text"] == "test_device_value"
        assert _objects(other)["p2b1"]["text"] == "global_value"
        assert device.source_of(_objects(device)["p2b1"]) is other.source_of(_objects(other)["p2b1"])

    def test_an_edit_of_a_shared_file_is_seen_by_the_other_device(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        label = _objects(other)["p2b2"]

        # WHEN
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")

        # THEN: the other device rendered it again, in the same dict, and told its listeners
        assert label["text"] == "changed"
        assert [(change.kind, change.objects) for change in changes] == [(ChangeKind.EDIT, [label])]
        assert device.is_dirty and other.is_dirty

    def test_objects_added_and_removed_in_a_shared_file_are_added_and_removed_for_the_other_device(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        [shared, _page] = device.components

        # WHEN
        device.add_object(shared.key, {"page": 2, "id": 3, "obj": "btn", "text": "{{ key_also_present_in_device_vars }}"})
        device.remove_object(_objects(device)["p2b1"])

        # THEN
        assert [object_name(obj) for obj in other.working_objects[shared.key]] == ["p2b2", "p2b3"]
        assert _objects(other)["p2b3"]["text"] == "global_value"
        assert [object_name(obj) for obj in changes[0].added] == ["p2b3"]
        assert changes[1].removed

        # WHEN: the other device edits the added object
        other.set_source_value(_objects(other)["p2b3"], "x", 7)

        # THEN
        assert _objects(device)["p2b3"]["x"] == 7

    def test_an_edit_of_a_shared_part_is_seen_by_the_other_device(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        tile = _objects(other)["p9b20"]
        focus = PartFocus(device, device.instance_of(_objects(device)["p9b20"]))

        # WHEN
        focus.set_source_value(_objects(device)["p9b20"], "text", "changed")

        # THEN
        assert tile["text"] == "changed"
        assert changes[0].objects == [tile]
        assert other.is_dirty
        assert [change.component.key for change in other.changes()] == [str(Path(other.part_keys[0]))]

    def test_the_files_of_a_device_are_its_own(self, devices, config):
        # GIVEN
        device, other = devices
        changes = _listened(other)

        # WHEN: the object of the same name in the own page of the device
        device.set_source_value(_objects(device)["p9b1"], "x", 50)

        # THEN
        assert _objects(other)["p9b1"]["x"] == 1
        assert changes == []
        assert not other.is_dirty and other.changes() == []
        assert [change.component.path.parent.name for change in config.changes()] == ["test_device"]

    def test_a_device_that_is_loaded_later_uses_the_draft_of_a_shared_file(self, cfg_root, config):
        # GIVEN
        device = load_session(cfg_root, config=config)
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")

        # WHEN
        other = load_session(cfg_root, OTHER_DEVICE, config)

        # THEN
        assert _objects(other)["p2b2"]["text"] == "changed"
        assert other.is_dirty
        assert device.undo_description == other.undo_description == "Change text of p2b2"


class TestSaving:
    def test_a_shared_file_is_saved_once_and_both_devices_have_no_changes_afterwards(self, devices, cfg_root):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")
        other.set_source_value(_objects(other)["p2b1"], "x", 3)

        # WHEN
        saved = plan_save(device)
        write_save(saved)
        device.mark_saved({change.path: change.content for change in saved})

        # THEN
        assert [change.path for change in saved] == [cfg_root / "common" / "shared.jsonl"]
        assert '"text": "changed"' in saved[0].content and '"x": 3' in saved[0].content
        assert not device.is_dirty and not other.is_dirty
        assert plan_save(other) == []
        assert changes[-1].kind == ChangeKind.SAVE

        # WHEN: an undo after saving
        other.undo()

        # THEN
        assert "x" not in _objects(device)["p2b1"] and "x" not in _objects(other)["p2b1"]
        assert device.is_dirty and other.is_dirty

    def test_a_device_saves_only_the_files_it_shows(self, devices):
        # GIVEN
        device, other = devices
        other.set_source_value(_objects(other)["p9b1"], "x", 3)
        device.set_source_value(_objects(device)["p9b1"], "x", 4)

        # WHEN
        saved = plan_save(device)
        device.mark_saved({change.path: change.content for change in saved})

        # THEN
        assert [change.path.parent.name for change in saved] == ["test_device"]
        assert other.is_dirty and not device.is_dirty


class TestUndo:
    def test_undo_and_redo_of_an_edit_of_a_shared_file_follow_on_both_devices(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")

        # WHEN
        undone = other.undo()

        # THEN
        assert _objects(device)["p2b2"]["text"] == _objects(other)["p2b2"]["text"] == "two"
        assert undone.kind == ChangeKind.UNDO and undone.objects == [_objects(other)["p2b2"]]
        assert changes[-1] is undone
        assert not device.is_dirty and not other.is_dirty

        # WHEN
        device.redo()

        # THEN
        assert _objects(device)["p2b2"]["text"] == _objects(other)["p2b2"]["text"] == "changed"
        assert changes[-1].kind == ChangeKind.REDO

    def test_undo_of_a_removed_object_of_a_shared_file_brings_it_back_on_both_devices(self, devices):
        # GIVEN
        device, other = devices
        uid = other.object_uid(_objects(other)["p2b1"])
        device.remove_object(_objects(device)["p2b1"])

        # WHEN
        device.undo()

        # THEN
        assert _objects(other)["p2b1"]["text"] == "global_value"
        assert other.object_uid(_objects(other)["p2b1"]) == uid
        assert [object_name(obj) for obj in other.working_objects[other.components[0].key]] == ["p2b1", "p2b2"]

    def test_undo_of_an_edit_of_a_shared_part(self, devices):
        # GIVEN
        device, other = devices
        focus = PartFocus(device, device.instance_of(_objects(device)["p9b20"]))
        focus.set_source_value(_objects(device)["p9b20"], "text", "changed")

        # WHEN
        other.undo()

        # THEN
        assert _objects(device)["p9b20"]["text"] == _objects(other)["p9b20"]["text"] == "tile"
        assert not device.is_dirty and not other.is_dirty

    def test_undo_of_an_edit_of_files_the_device_does_not_show_changes_nothing_of_it(self, devices):
        # GIVEN: one history for all devices
        device, other = devices
        changes = _listened(other)
        device.set_source_value(_objects(device)["p9b1"], "x", 50)

        # WHEN
        undone = other.undo()

        # THEN
        assert _objects(device)["p9b1"]["x"] == 1
        assert (undone.objects, undone.pages, changes) == ([], set(), [])


class TestLoading:
    def test_a_changed_shared_file_is_loaded_again_and_the_other_device_follows(self, devices, cfg_root):
        # GIVEN
        device, other = devices
        (cfg_root / "common" / "shared.jsonl").write_text(SHARED_JSONL.replace('"two"', '"three"'))

        # WHEN
        reloaded = load_session(cfg_root, config=device.config)

        # THEN
        assert _objects(reloaded)["p2b2"]["text"] == "three"
        assert _objects(other)["p2b2"]["text"] == "three"
        assert other.source_of(_objects(other)["p2b2"]) is reloaded.source_of(_objects(reloaded)["p2b2"])

    def test_a_shared_file_with_changes_is_not_loaded_again(self, devices, cfg_root):
        # GIVEN
        device, other = devices
        other.set_source_value(_objects(other)["p2b2"], "text", "changed")
        (cfg_root / "common" / "shared.jsonl").write_text(SHARED_JSONL.replace('"two"', '"three"'))

        # WHEN
        reloaded = load_session(cfg_root, config=device.config)

        # THEN
        assert _objects(reloaded)["p2b2"]["text"] == "changed"
        assert reloaded.undo_description == "Change text of p2b2"

    def test_reverting_a_device_reverts_the_shared_files_for_the_other_device_and_forgets_their_history(self, devices):
        # GIVEN
        device, other = devices
        other.set_source_value(_objects(other)["p9b1"], "x", 3)
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")

        # WHEN
        device.reset_to_disk()

        # THEN: the own file of the other device keeps its change, and its edit can still be undone
        assert _objects(other)["p2b2"]["text"] == "two"
        assert _objects(other)["p9b1"]["x"] == 3
        assert not device.is_dirty and other.is_dirty
        assert other.undo_description == "Change x of p9b1"

    def test_a_discarded_draft_leaves_the_files_as_they_were_loaded(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(device)
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")

        # WHEN
        device.discard()

        # THEN
        assert _objects(other)["p2b2"]["text"] == "two"
        assert not other.is_dirty and not device.is_loaded
        assert other.undo_description is None

        # WHEN: the other device edits the file
        other.set_source_value(_objects(other)["p2b2"], "text", "again")

        # THEN: the discarded draft doesn't follow
        assert len(changes) == 1


class TestWindow:
    def test_another_device_shows_the_draft_of_a_shared_file_and_reverting_it_reverts_the_file(self, window):
        # GIVEN
        window.session.set_source_value(_objects(window.session)["p2b2"], "text", "changed")

        # WHEN
        window.on_device_selected(OTHER_DEVICE)
        wait_until(lambda: window.device is not None and window.device.name == OTHER_DEVICE)

        # THEN
        assert _objects(window.session)["p2b2"]["text"] == "changed"
        assert window.session.is_dirty and window.action_save.isEnabled()

        # WHEN
        window.reload_draft()
        wait_until(lambda: window.device is not None and window.session.is_loaded and not window.session.is_dirty)

        # THEN
        assert _objects(window.session)["p2b2"]["text"] == "two"
        assert not window.sessions[("test_device", "boot.cmd")].is_dirty
