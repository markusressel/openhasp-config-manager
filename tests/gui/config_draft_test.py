from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from openhasp_config_manager.gui.domain.draft.config_draft import ConfigDraft, UndoRefusedError
from openhasp_config_manager.gui.domain.draft.files import plan_save, write_save
from openhasp_config_manager.gui.domain.draft.model import ChangeKind, DraftChange
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
        device.enter_part_mode(device.instance_of(_objects(device)["p9b20"]))

        # WHEN
        device.set_source_value(_objects(device)["p9b20"], "text", "changed")

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
        device.enter_part_mode(device.instance_of(_objects(device)["p9b20"]))
        device.set_source_value(_objects(device)["p9b20"], "text", "changed")

        # WHEN
        other.undo()

        # THEN
        assert _objects(device)["p9b20"]["text"] == _objects(other)["p9b20"]["text"] == "tile"
        assert not device.is_dirty and not other.is_dirty

    def test_undo_does_not_undo_the_own_files_of_another_device(self, devices):
        # GIVEN
        device, other = devices
        changes = _listened(other)
        device.set_source_value(_objects(device)["p9b1"], "x", 50)

        # WHEN
        undone = other.undo()

        # THEN
        assert undone is None
        assert _objects(device)["p9b1"]["x"] == 50
        assert (other.undo_description, device.undo_description) == (None, "Change x of p9b1")
        assert changes == []

    def test_each_device_undoes_the_newest_edit_of_the_files_it_shows(self, devices):
        # GIVEN: an edit of the shared file, of the own file of each device, and of the shared part
        device, other = devices
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")
        other.set_source_value(_objects(other)["p9b1"], "x", 3)
        device.set_source_value(_objects(device)["p9b1"], "x", 4)
        other.enter_part_mode(other.instance_of(_objects(other)["p9b20"]))
        other.set_source_value(_objects(other)["p9b20"], "text", "part")
        other.leave_part_mode()

        # WHEN: the device undoes twice
        device.undo()
        device.undo()

        # THEN: the edit of the part (shown by both), then its own one; the own edit of the other device stays
        assert _objects(device)["p9b20"]["text"] == _objects(other)["p9b20"]["text"] == "tile"
        assert _objects(device)["p9b1"]["x"] == 1 and _objects(other)["p9b1"]["x"] == 3
        assert (device.undo_description, other.undo_description) == ("Change text of p2b2", "Change x of p9b1")

        # WHEN: the other device undoes twice
        other.undo()
        other.undo()

        # THEN: its own edit, then the one of the device in the shared file
        assert _objects(other)["p9b1"]["x"] == 1
        assert _objects(device)["p2b2"]["text"] == _objects(other)["p2b2"]["text"] == "two"
        assert device.undo() is None and other.undo() is None
        assert not device.is_dirty and not other.is_dirty

    def test_an_edit_of_several_files_is_undone_as_a_whole_and_only_if_it_is_the_newest_in_each(self, devices):
        # GIVEN: one step in the shared file and in the own file of the device, then another edit of its own file
        device, other = devices
        with device.edit("Change both"):
            device.set_source_value(_objects(device)["p2b2"], "text", "changed")
            device.set_source_value(_objects(device)["p9b1"], "x", 5)
        device.set_source_value(_objects(device)["p9b1"], "x", 6)

        # THEN: the other device would undo it, but it is refused
        step = other.next_undo
        assert step.description == "Change both"
        assert other.display_paths(step.files) == ["common/shared.jsonl", f"{DEVICE_DIR}/page.jsonl"]
        assert other.display_paths(step.changed_since) == [f"{DEVICE_DIR}/page.jsonl"]

        # WHEN
        with pytest.raises(UndoRefusedError, match=f"{DEVICE_DIR}/page.jsonl changed since"):
            other.undo()

        # THEN: nothing changed
        assert _objects(other)["p2b2"]["text"] == "changed"
        assert _objects(device)["p9b1"]["x"] == 6

        # WHEN: the newer edit is undone
        device.undo()

        # THEN: the other device undoes the step in both files
        assert other.next_undo.changed_since == frozenset()
        other.undo()
        assert _objects(device)["p2b2"]["text"] == _objects(other)["p2b2"]["text"] == "two"
        assert _objects(device)["p9b1"]["x"] == 1
        assert device.undo_description is None

    def test_redo_of_an_edit_of_several_files_waits_for_the_steps_to_redo_before_it_in_its_files(self, devices):
        # GIVEN: an edit of the own file of the device, then a step of both files; both undone
        device, other = devices
        device.set_source_value(_objects(device)["p9b1"], "x", 5)
        with device.edit("Change both"):
            device.set_source_value(_objects(device)["p2b2"], "text", "changed")
            device.set_source_value(_objects(device)["p9b1"], "x", 6)
        device.undo()
        device.undo()

        # WHEN: the other device redoes the step before the edit it followed
        with pytest.raises(UndoRefusedError, match="Can't redo"):
            other.redo()

        # THEN
        assert other.redo_description == "Change both"
        assert other.display_paths(other.next_redo.changed_since) == [f"{DEVICE_DIR}/page.jsonl"]
        assert _objects(device)["p9b1"]["x"] == 1

        # WHEN: the device redoes its own edit first
        device.redo()
        other.redo()

        # THEN
        assert _objects(device)["p9b1"]["x"] == 6
        assert _objects(device)["p2b2"]["text"] == _objects(other)["p2b2"]["text"] == "changed"
        assert device.redo_description is None and other.undo_description == "Change both"

    def test_an_edit_drops_only_what_could_be_redone_in_its_files(self, devices):
        # GIVEN: an undone edit of the shared file, and an undone edit of the own file of the other device
        device, other = devices
        device.set_source_value(_objects(device)["p2b2"], "text", "changed")
        other.set_source_value(_objects(other)["p9b1"], "x", 3)
        other.undo()
        other.undo()

        # WHEN: an edit of the own file of the device
        device.set_source_value(_objects(device)["p9b1"], "x", 4)

        # THEN: both can still be redone
        assert (device.redo_description, other.redo_description) == ("Change text of p2b2", "Change text of p2b2")

        # WHEN: an edit of the shared file
        device.set_source_value(_objects(device)["p2b1"], "x", 7)

        # THEN
        assert (device.redo_description, other.redo_description) == (None, "Change x of p9b1")

    def test_typing_through_one_device_is_merged_into_one_step(self, devices):
        # GIVEN
        device, other = devices
        label = _objects(device)["p2b2"]

        # WHEN
        for text in ["a", "ab", "abc"]:
            with device.edit("Change text of p2b2", merge_key=("text", device.object_uid(label))):
                device.set_source_value(label, "text", text)

        # THEN
        other.undo()
        assert _objects(device)["p2b2"]["text"] == "two"
        assert other.undo_description is None


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
