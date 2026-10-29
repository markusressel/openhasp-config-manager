import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft.files import load_device, plan_save
from openhasp_config_manager.gui.domain.draft.session import PlateSession, ReadOnlyObjectError
from openhasp_config_manager.gui.domain.problems import object_name

DEVICE = "devices/test_device"

PAGE_JSONL = """// a page with tiles
{"page": 9, "id": 1, "obj": "obj", "y": 10, "h": 20}
{
  // two tiles below object 1
  "!include": "common/parts/tile.jsonl",
  "vars": {"anchor": 1},
  "for": {"id": [20, 30]}
}
{"page": 9, "id": 2, "obj": "label", "x": "{{ b20.x + 5 }}"}
"""

TILE_JSONL = """// the caption and the value
{"page": 9, "id": "{{ id }}", "obj": "label", "x": "{{ id * 2 }}", "y": "{{ b{{ anchor }}.y + b{{ anchor }}.h }}"}
{"page": 9, "id": "{{ id + 1 }}", "obj": "label", "x": "{{ id * 2 }}", "text": "{{ id }}"}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / "common" / "parts").mkdir()
    (root / "common" / "parts" / "tile.jsonl").write_text(TILE_JSONL)
    _write_page(root, PAGE_JSONL)
    return root


def _write_page(root: Path, content: str):
    (root / DEVICE / "page.jsonl").write_text(content)
    (root / DEVICE / "boot.cmd").write_text("run L:/page.jsonl\n")


def _load(cfg_root: Path) -> PlateSession:
    loaded = load_device(_create_config_manager(cfg_root, cfg_root.parent / "output"), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)
    return session


def _objects(session: PlateSession):
    [component] = session.components
    return {object_name(obj): obj for obj in session.working_objects[component.key]}


class TestIncludedObjects:
    def test_the_included_objects_are_in_place_of_the_directive(self, cfg_root):
        # WHEN
        session = _load(cfg_root)

        # THEN
        [component] = session.components
        assert [object_name(obj) for obj in session.working_objects[component.key]] == [
            "p9b1",
            "p9b20",
            "p9b21",
            "p9b30",
            "p9b31",
            "p9b2",
        ]
        objects = _objects(session)
        assert (objects["p9b20"]["x"], objects["p9b20"]["y"], objects["p9b31"]["text"]) == (40, 30, "30")
        assert objects["p9b2"]["x"] == 45
        assert session.is_dirty is False
        assert session.changes() == []

    def test_where_an_included_object_is_written(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        objects = _objects(session)

        # THEN: its line is the one of the directive, its origin says where it is written
        tile = objects["p9b31"]
        assert session.is_included(tile) and not session.is_included(objects["p9b1"])
        assert session.line_of(tile) == 3
        origin = session.origin_of(tile)
        assert (origin.file, origin.line) == (cfg_root / "common/parts/tile.jsonl", 3)
        assert [(step.line, step.loop) for step in origin.includes] == [(3, {"id": 30})]
        assert session.origin_of(objects["p9b1"]) is None
        assert session.source_of(tile)["text"] == "{{ id }}"
        assert session.read_only_reason(tile) == (
            f"It is included from common/parts/tile.jsonl:3 (included at {DEVICE}/page.jsonl:3 (id=30)). "
            "Change it in that file, or the vars of the !include."
        )
        assert session.read_only_reason(objects["p9b1"]) is None

    def test_the_cursor_in_a_directive_selects_nothing(self, cfg_root):
        session = _load(cfg_root)
        [component] = session.components

        assert session.object_of_source(component.key, 1) is None
        assert object_name(session.object_of_source(component.key, 2)) == "p9b2"

    def test_included_objects_are_read_only(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        tile = _objects(session)["p9b20"]

        # THEN
        assert session.check_value(tile, "x", 5).startswith("It is included from common/parts/tile.jsonl:2")
        for change in (
            lambda: session.set_source_value(tile, "x", 5),
            lambda: session.remove_source_value(tile, "x"),
            lambda: session.use_pixel_position(tile),
            lambda: session.duplicate_object(tile),
            lambda: session.remove_object(tile),
        ):
            with pytest.raises(ReadOnlyObjectError, match="^p9b20 can't be changed here. It is included from"):
                change()
        assert session.undo_description is None
        assert session.is_dirty is False

    def test_templates_of_an_included_object_see_its_instance(self, cfg_root):
        session = _load(cfg_root)
        tile = _objects(session)["p9b30"]

        assert session.check_template(tile, "{{ id + anchor }}") is None
        assert session.check_template(tile, "{{ nope }}") is not None

    def test_an_included_object_follows_the_object_it_refers_to(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        objects = _objects(session)

        # WHEN
        session.set_source_value(objects["p9b1"], "h", 50)

        # THEN
        assert (objects["p9b20"]["y"], objects["p9b30"]["y"]) == (60, 60)

        # WHEN
        session.undo()

        # THEN
        assert (objects["p9b20"]["y"], objects["p9b30"]["y"]) == (30, 30)
        assert session.is_dirty is False

    def test_undo_and_redo_keep_the_included_objects(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        [component] = session.components

        # WHEN
        session.remove_object(_objects(session)["p9b1"])
        session.undo()
        session.redo()

        # THEN
        assert [object_name(obj) for obj in session.working_objects[component.key]] == [
            "p9b20",
            "p9b21",
            "p9b30",
            "p9b31",
            "p9b2",
        ]
        assert session.is_dirty is True


class TestSave:
    def test_save_keeps_the_directive_and_writes_only_the_objects_of_the_file(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        objects = _objects(session)
        [component] = session.components

        # WHEN: an object before the directive is removed, one after it is changed, one is added
        session.remove_object(objects["p9b1"])
        session.set_source_value(objects["p9b2"], "y", 7)
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "obj"})
        [change] = plan_save(session)

        # THEN
        assert change.content == (
            "// a page with tiles\n"
            "{\n"
            "  // two tiles below object 1\n"
            '  "!include": "common/parts/tile.jsonl",\n'
            '  "vars": {"anchor": 1},\n'
            '  "for": {"id": [20, 30]}\n'
            "}\n"
            '{"page": 9, "id": 2, "obj": "label", "x": "{{ b20.x + 5 }}", "y": 7}\n'
            '{"page": 9, "id": 3, "obj": "obj"}\n'
        )

    def test_after_a_save_the_draft_goes_on_from_the_new_files(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        objects = _objects(session)
        [component] = session.components
        session.remove_object(objects["p9b1"])
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "obj"})
        [change] = plan_save(session)
        change.path.write_text(change.content)

        # WHEN
        session.mark_saved({change.path: change.content})

        # THEN: the directive moved up a line
        assert session.is_dirty is False
        assert session.line_of(objects["p9b30"]) == 2
        assert [source.get("id") for source in session.components[0].sources] == [None, 2, 3]

        # WHEN: another change is saved
        session.set_source_value(_objects(session)["p9b3"], "x", 4)
        [change] = plan_save(session)

        # THEN
        assert change.content.endswith('{"page": 9, "id": 3, "obj": "obj", "x": 4}\n')
        assert '"!include": "common/parts/tile.jsonl"' in change.content

        # WHEN: undoing the change, the addition and the removal from before the save
        session.undo()
        session.undo()
        session.undo()

        # THEN: the removed object comes back as a new one, which is saved at the end of the file
        assert session.is_dirty is True
        assert [object_name(obj) for obj in session.working_objects[component.key]][0] == "p9b1"
        [change] = plan_save(session)
        assert change.content.endswith('"x": "{{ b20.x + 5 }}"}\n{"page": 9, "id": 1, "obj": "obj", "y": 10, "h": 20}\n')

    def test_a_directive_that_includes_nothing_is_kept(self, cfg_root):
        # GIVEN: the part doesn't exist
        _write_page(cfg_root, '{"!include": "common/parts/nope.jsonl"}\n{"page": 9, "id": 1, "obj": "obj"}\n')
        session = _load(cfg_root)
        [component] = session.components

        # WHEN
        session.set_source_value(_objects(session)["p9b1"], "x", 3)
        [change] = plan_save(session)

        # THEN
        assert change.content == '{"!include": "common/parts/nope.jsonl"}\n{"page": 9, "id": 1, "obj": "obj", "x": 3}\n'
        [error] = session.include_errors()[component.key]
        assert (error.line, error.message) == (1, "The file to include doesn't exist: common/parts/nope.jsonl")
