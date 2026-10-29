import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft.files import SaveConflictError, load_device, plan_save
from openhasp_config_manager.gui.domain.draft.part_ids import new_part_object_ids
from openhasp_config_manager.gui.domain.draft.session import PlateSession, ReadOnlyObjectError
from openhasp_config_manager.gui.domain.problems import object_name

DEVICE = "devices/test_device"

PAGE_JSONL = """{"page": 9, "id": 1, "obj": "obj", "y": 10, "h": 20}
{"!include": "common/parts/tile.jsonl", "vars": {"page": 9}, "for": {"id": [20, 30]}}
{"!include": "common/parts/tile.jsonl", "vars": {"page": 8, "id": 50}}
{"page": 9, "id": 2, "obj": "label", "x": "{{ p8b51.y + 1 }}"}
"""

TILE_JSONL = """// the caption and the value
{"page": "{{ page }}", "id": "{{ id }}", "obj": "label", "x": "{{ id * 2 }}", "y": 10, "text": "{{ id }}"}
{"page": "{{ page }}", "id": "{{ id + 1 }}", "obj": "label", "x": 5, "y": 40, "text": "v"}
"""

NESTED_JSONL = """{"page": "{{ page }}", "id": "{{ id + 5 }}", "obj": "obj", "x": 1}
{"!include": "common/parts/dot.jsonl", "vars": {"dot": "{{ id + 6 }}"}}
"""

DOT_JSONL = '{"page": "{{ page }}", "id": "{{ dot }}", "obj": "obj", "x": 2}\n'


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / "common" / "parts").mkdir()
    (root / "common" / "parts" / "tile.jsonl").write_text(TILE_JSONL)
    (root / DEVICE / "page.jsonl").write_text(PAGE_JSONL)
    (root / DEVICE / "boot.cmd").write_text("run L:/page.jsonl\n")
    return root


@pytest.fixture
def tile(cfg_root) -> Path:
    return cfg_root / "common" / "parts" / "tile.jsonl"


def _load(cfg_root: Path) -> PlateSession:
    loaded = load_device(_create_config_manager(cfg_root, cfg_root.parent / "output"), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)
    return session


@pytest.fixture
def session(cfg_root) -> PlateSession:
    return _load(cfg_root)


def _objects(session: PlateSession):
    return {object_name(obj): obj for objects in session.working_objects.values() for obj in objects}


def _edit_the_part(session: PlateSession, name: str = "p9b20"):
    session.enter_part_mode(session.instance_of(_objects(session)[name]))


class TestPartMode:
    def test_the_instances_of_a_part(self, session, tile):
        # WHEN
        instances = session.part_instances(tile)

        # THEN
        assert [session.describe_instance(instance) for instance in instances] == [
            f"{DEVICE}/page.jsonl:2 (id=20)",
            f"{DEVICE}/page.jsonl:2 (id=30)",
            f"{DEVICE}/page.jsonl:3",
        ]
        assert [session.page_of_instance(instance) for instance in instances] == [9, 9, 8]
        assert session.instance_of(_objects(session)["p9b31"]) == instances[1]
        assert [object_name(obj) for obj in session.objects_of_instance(instances[2])] == ["p8b50", "p8b51"]

    def test_only_the_objects_of_the_instance_can_be_changed(self, session, tile):
        # GIVEN
        objects = _objects(session)
        assert session.read_only_reason(objects["p9b20"]) is not None

        # WHEN
        _edit_the_part(session)

        # THEN
        assert session.part_mode.part == tile
        assert session.read_only_reason(objects["p9b20"]) is None
        assert [name for name, obj in objects.items() if session.is_selectable(obj)] == ["p9b20", "p9b21"]
        assert session.read_only_reason(objects["p9b30"]) == (
            "In part mode only the objects of the part common/parts/tile.jsonl (of the instance that is shown) can be changed."
        )
        with pytest.raises(ReadOnlyObjectError):
            session.set_source_value(objects["p9b1"], "x", 3)

    def test_an_edit_of_a_part_object_changes_every_instance_and_saves_only_the_part(self, session, tile):
        # GIVEN
        _edit_the_part(session)
        objects = _objects(session)

        # WHEN
        session.set_source_value(objects["p9b20"], "x", "{{ id * 3 }}")
        session.set_source_value(objects["p9b21"], "text", "w")

        # THEN: each instance with its own variables, the objects stay
        after = _objects(session)
        assert all(after[name] is obj for name, obj in objects.items())
        assert [after[name]["x"] for name in ("p9b20", "p9b30", "p8b50")] == [60, 90, 150]
        assert [after[name]["text"] for name in ("p9b21", "p9b31", "p8b51")] == ["w", "w", "w"]
        assert session.is_dirty is True

        # WHEN
        [change] = plan_save(session)

        # THEN
        assert change.path == tile and change.is_common is True
        assert change.content == (
            "// the caption and the value\n"
            '{"page": "{{ page }}", "id": "{{ id }}", "obj": "label", "x": "{{ id * 3 }}", "y": 10, "text": "{{ id }}"}\n'
            '{"page": "{{ page }}", "id": "{{ id + 1 }}", "obj": "label", "x": 5, "y": 40, "text": "w"}\n'
        )

    def test_a_move_changes_the_position_of_every_instance(self, session):
        # GIVEN
        _edit_the_part(session)

        # WHEN: like a drag
        with session.edit("Move p9b21"):
            session.set_source_value(_objects(session)["p9b21"], "x", 7)
            session.set_source_value(_objects(session)["p9b21"], "y", 8)

        # THEN
        objects = _objects(session)
        assert [(objects[name]["x"], objects[name]["y"]) for name in ("p9b21", "p9b31", "p8b51")] == [(7, 8)] * 3
        # p9b2 refers to p8b51
        assert objects["p9b2"]["x"] == 9
        assert session.undo_description == "Move p9b21"

    def test_adding_and_removing_objects_of_a_part(self, session, tile):
        # GIVEN
        _edit_the_part(session)
        changes = []
        session.add_listener(changes.append)

        # WHEN
        added = session.add_object(str(tile), {"page": 9, "id": 99, "obj": "btn", "x": 1})

        # THEN: in every instance, with templates for the page and id
        assert object_name(added) == "p9b22"
        assert session.source_of(added) == {"page": "{{ page }}", "id": "{{ id + 2 }}", "obj": "btn", "x": 1}
        assert {"p9b22", "p9b32", "p8b52"} <= set(_objects(session))
        assert changes[-1].selected == [added]
        assert session.is_selectable(added)

        # WHEN
        session.remove_object(_objects(session)["p9b21"])

        # THEN
        assert not {"p9b21", "p9b31", "p8b51"} & set(_objects(session))
        assert _objects(session)["p9b2"]["x"] == "{{ p8b51.y + 1 }}"

        # WHEN
        session.undo()
        session.undo()

        # THEN
        objects = _objects(session)
        assert {"p9b21", "p9b31", "p8b51"} <= set(objects) and not {"p9b22", "p9b32"} & set(objects)
        assert objects["p9b2"]["x"] == 41
        assert session.is_dirty is False
        assert session.changes() == []

        # WHEN
        session.redo()
        [change] = plan_save(session)

        # THEN: at the end of the part
        assert change.content.endswith('{"page": "{{ page }}", "id": "{{ id + 2 }}", "obj": "btn", "x": 1}\n')

    def test_duplicating_a_part_object(self, session):
        # GIVEN
        _edit_the_part(session)

        # WHEN
        duplicate = session.duplicate_object(_objects(session)["p9b21"])

        # THEN
        assert session.source_of(duplicate)["id"] == "{{ id + 2 }}"
        assert (duplicate["x"], duplicate["y"]) == (15, 50)

    def test_objects_cant_be_pasted_into_a_part(self, session, tile):
        _edit_the_part(session)

        with pytest.raises(ValueError, match="can't be pasted into a part"):
            session.paste_objects(str(tile), [{"page": 9, "id": 3, "obj": "btn"}], page=9, screen=(480, 480))

    def test_leaving_part_mode_keeps_the_changes_and_switching_the_instance_too(self, session, tile):
        # GIVEN
        _edit_the_part(session)
        session.set_source_value(_objects(session)["p9b21"], "text", "w")

        # WHEN
        session.enter_part_mode(session.part_instances(tile)[2])

        # THEN
        objects = _objects(session)
        assert objects["p8b51"]["text"] == "w"
        assert session.read_only_reason(objects["p8b51"]) is None and session.read_only_reason(objects["p9b21"]) is not None

        # WHEN
        session.leave_part_mode()

        # THEN
        assert session.part_mode is None
        assert session.is_dirty is True and objects["p9b21"]["text"] == "w"
        assert session.read_only_reason(objects["p9b21"]).startswith("It is included from")

    def test_a_part_that_changed_on_disk_is_not_overwritten(self, session, tile):
        # GIVEN
        _edit_the_part(session)
        session.set_source_value(_objects(session)["p9b21"], "text", "w")
        tile.write_text(TILE_JSONL + "\n")

        # THEN
        with pytest.raises(SaveConflictError, match="tile.jsonl changed on disk"):
            plan_save(session)

    def test_after_a_save_the_part_goes_on_from_its_new_content(self, session, tile):
        # GIVEN: an object of the part is removed and saved
        _edit_the_part(session)
        session.remove_object(_objects(session)["p9b20"])
        [change] = plan_save(session)
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # THEN
        assert session.is_dirty is False
        assert session.origin_of(_objects(session)["p9b31"]).line == 2

        # WHEN: another change is saved, then both are undone
        session.set_source_value(_objects(session)["p9b21"], "text", "w")
        [change] = plan_save(session)
        assert change.content.endswith('"text": "w"}\n')
        session.undo()
        session.undo()

        # THEN: the removed object comes back at the end of the part
        assert {"p9b20", "p9b30", "p8b50"} <= set(_objects(session))
        [change] = plan_save(session)
        assert change.content.endswith('"x": "{{ id * 2 }}", "y": 10, "text": "{{ id }}"}\n')

    def test_a_directive_after_a_saved_removal_keeps_its_part_mode(self, session, cfg_root):
        # GIVEN: the object before the directives is removed, then part mode is entered and the file saved
        instance = session.instance_of(_objects(session)["p9b30"])
        session.remove_object(_objects(session)["p9b1"])
        session.enter_part_mode(instance)
        [change] = plan_save(session)
        change.path.write_text(change.content)

        # WHEN
        session.mark_saved({change.path: change.content})

        # THEN: the directive is the first object of the file now
        assert session.part_mode in session.part_instances(instance.part)
        assert session.describe_instance(session.part_mode) == f"{DEVICE}/page.jsonl:1 (id=30)"
        assert session.read_only_reason(_objects(session)["p9b30"]) is None

    def test_a_page_file_cant_be_edited_as_a_part(self, cfg_root):
        # GIVEN: a page file that is also included
        (cfg_root / DEVICE / "other.jsonl").write_text('{"page": 7, "id": 1, "obj": "obj"}\n')
        (cfg_root / DEVICE / "page.jsonl").write_text(f'{{"!include": "{DEVICE}/other.jsonl", "vars": {{"x": 1}}}}\n')
        (cfg_root / DEVICE / "boot.cmd").write_text("run L:/page.jsonl\nrun L:/other.jsonl\n")
        session = _load(cfg_root)
        [included] = session.working_objects[str(cfg_root / DEVICE / "page.jsonl")]

        # THEN
        with pytest.raises(ValueError, match="is also a page file of the device"):
            session.enter_part_mode(session.instance_of(included))


class TestNestedParts:
    @pytest.fixture
    def session(self, cfg_root) -> PlateSession:
        (cfg_root / "common" / "parts" / "tile.jsonl").write_text(TILE_JSONL + NESTED_JSONL.split("\n", 1)[1])
        (cfg_root / "common" / "parts" / "dot.jsonl").write_text(DOT_JSONL)
        return _load(cfg_root)

    def test_the_objects_of_an_inner_part_are_selectable_but_not_editable(self, session, cfg_root):
        # GIVEN
        _edit_the_part(session)
        dot = _objects(session)["p9b26"]

        # THEN
        assert session.is_selectable(dot)
        assert session.read_only_reason(dot) == (
            "It is included from common/parts/dot.jsonl:1, by an !include inside of the part common/parts/tile.jsonl: "
            "edit that part."
        )
        inner = session.instance_of(dot)
        assert inner.part == cfg_root / "common/parts/dot.jsonl"
        assert session.instance_of(dot, cfg_root / "common/parts/tile.jsonl") == session.part_mode

    def test_an_edit_of_the_inner_part_changes_its_instances_in_every_outer_instance(self, session):
        # GIVEN
        session.enter_part_mode(session.instance_of(_objects(session)["p9b26"]))

        # WHEN
        session.set_source_value(_objects(session)["p9b26"], "x", 9)

        # THEN
        objects = _objects(session)
        assert [objects[name]["x"] for name in ("p9b26", "p9b36", "p8b56")] == [9, 9, 9]
        assert [change.component.path.name for change in session.changes()] == ["dot.jsonl"]


class TestNewPartObjectIds:
    @pytest.mark.parametrize(
        "ids, expected",
        [
            (["{{ id }}", "{{ id + 1 }}"], "{{ id + 2 }}"),
            (["{{ ids.base + 4 }}", "{{ ids.base }}"], "{{ ids.base + 5 }}"),
            (["{{ id }}", "{{ other }}"], 7),
            (["{{ id }}", 12], 7),
            ([], 7),
        ],
    )
    def test_the_id(self, ids, expected):
        sources = [{"page": "{{ page }}", "id": object_id} for object_id in ids]

        assert new_part_object_ids(sources, {"page": 3, "id": 7}) == ("{{ page }}" if ids else 3, expected)

    def test_the_page_is_the_template_most_objects_use(self):
        sources = [{"page": "{{ a }}"}, {"page": "{{ b }}"}, {"page": "{{ b }}"}, {"page": 2}]

        assert new_part_object_ids(sources, {"page": 3, "id": 7})[0] == "{{ b }}"
