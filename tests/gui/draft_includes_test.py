from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.draft.files import plan_save
from openhasp_config_manager.gui.domain.draft.session import InvalidDirectiveError, PlateSession, ReadOnlyObjectError
from openhasp_config_manager.gui.domain.problems import object_name
from tests.helpers import copy_test_config, load_session, write_page

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
    root = copy_test_config(tmp_path, {"common/parts/tile.jsonl": TILE_JSONL})
    _write_page(root, PAGE_JSONL)
    return root


def _write_page(root: Path, content: str):
    write_page(root, content, "page.jsonl")


def _objects(session: PlateSession):
    [component] = session.components
    return {object_name(obj): obj for obj in session.working_objects[component.key]}


class TestIncludedObjects:
    def test_the_included_objects_are_in_place_of_the_directive(self, cfg_root):
        # WHEN
        session = load_session(cfg_root)

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
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
        [component] = session.components

        assert session.object_of_source(component.key, 1) is None
        assert object_name(session.object_of_source(component.key, 2)) == "p9b2"

    def test_included_objects_are_read_only(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
        tile = _objects(session)["p9b30"]

        assert session.check_template(tile, "{{ id + anchor }}") is None
        assert session.check_template(tile, "{{ nope }}") is not None

    def test_an_included_object_follows_the_object_it_refers_to(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
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
        session = load_session(cfg_root)
        [component] = session.components

        # WHEN
        session.set_source_value(_objects(session)["p9b1"], "x", 3)
        [change] = plan_save(session)

        # THEN
        assert change.content == '{"!include": "common/parts/nope.jsonl"}\n{"page": 9, "id": 1, "obj": "obj", "x": 3}\n'
        [error] = session.include_errors()[component.key]
        assert (error.line, error.message) == (1, "The file to include doesn't exist: common/parts/nope.jsonl")


DIRECTIVE_PAGE_JSONL = """// tiles below an anchor
{"page": 9, "id": 1, "obj": "obj", "y": 10, "h": 20}
{"page": 9, "id": 2, "obj": "obj", "y": 50, "h": 30}
{
  // the tiles
  "!include": "common/parts/tile.jsonl",
  "vars": {"anchor": 1},
  "for": {"id": [20, 30]}
}
{"page": 9, "id": 3, "obj": "label", "x": "{{ b20.x + 5 }}", "y": "{{ b20.y }}"}
"""


class TestDirectiveEdits:
    @pytest.fixture
    def session(self, cfg_root) -> PlateSession:
        _write_page(cfg_root, DIRECTIVE_PAGE_JSONL)
        return load_session(cfg_root)

    def test_a_var_edit_renders_the_instances_again_and_is_saved_into_the_directive(self, session):
        # GIVEN
        objects = _objects(session)
        tile = objects["p9b30"]
        assert session.directive_of(tile)["vars"] == {"anchor": 1}
        changes = []
        session.add_listener(changes.append)

        # WHEN
        session.set_directive_value(tile, "vars", {"anchor": 2})

        # THEN: the objects stay, with the new values
        after = _objects(session)
        assert all(after[name] is objects[name] for name in objects)
        assert [after[name]["y"] for name in ("p9b20", "p9b30")] == [80, 80]
        assert session.directive_of(tile)["vars"] == {"anchor": 2}
        assert session.origin_of(tile).includes[0].vars == {"anchor": 2}
        assert session.is_dirty is True
        [change] = changes
        assert change.selected == [tile] and not change.adds_or_removes
        # the scope of every object of the instances changed, and p9b3 refers to p9b20
        assert {object_name(obj) for obj in change.objects} == {"p9b20", "p9b21", "p9b30", "p9b31"}
        assert after["p9b3"]["y"] == 80

        # WHEN
        [change] = plan_save(session)

        # THEN: only the vars changed
        assert change.content == DIRECTIVE_PAGE_JSONL.replace('"vars": {"anchor": 1}', '"vars": {"anchor": 2}')

    def test_an_object_that_refers_to_an_included_object_follows_a_var_edit(self, session):
        # GIVEN
        label = _objects(session)["p9b3"]
        assert label["y"] == 30

        # WHEN
        session.set_directive_value(_objects(session)["p9b20"], "vars", {"anchor": 2})

        # THEN
        assert label["y"] == 80

    def test_a_for_edit_adds_and_removes_instances_and_undo_restores_them(self, session):
        # GIVEN
        [component] = session.components
        objects = _objects(session)
        tile = objects["p9b30"]

        # WHEN
        session.set_directive_value(tile, "for", {"id": [30, 40]})

        # THEN: the instance of 30 stays, 20 is gone, 40 is new, in the place of the directive
        names = [object_name(obj) for obj in session.working_objects[component.key]]
        assert names == ["p9b1", "p9b2", "p9b30", "p9b31", "p9b40", "p9b41", "p9b3"]
        assert _objects(session)["p9b30"] is tile
        assert _objects(session)["p9b41"]["text"] == "40"
        assert session.origin_of(_objects(session)["p9b40"]).includes[0].loop == {"id": 40}

        # WHEN
        session.undo()

        # THEN
        names = [object_name(obj) for obj in session.working_objects[component.key]]
        assert names == ["p9b1", "p9b2", "p9b20", "p9b21", "p9b30", "p9b31", "p9b3"]
        restored = _objects(session)
        assert restored["p9b30"] is tile and restored["p9b1"] is objects["p9b1"]
        assert session.origin_of(restored["p9b20"]).includes[0].loop == {"id": 20}
        assert restored["p9b3"]["x"] == 45
        assert session.is_dirty is False
        assert session.changes() == []

        # WHEN
        session.redo()

        # THEN
        assert [object_name(obj) for obj in session.working_objects[component.key]][2:6] == [
            "p9b30",
            "p9b31",
            "p9b40",
            "p9b41",
        ]
        assert session.directive_of(tile)["for"] == {"id": [30, 40]}

    def test_an_instance_that_is_gone_is_not_selected(self, session):
        # GIVEN
        changes = []
        session.add_listener(changes.append)

        # WHEN
        session.set_directive_value(_objects(session)["p9b20"], "for", {"id": [30]})

        # THEN
        assert changes[0].selected == [] and changes[0].removed

    def test_an_edit_that_collides_ids_is_refused(self, session):
        # GIVEN
        before = {name: dict(obj) for name, obj in _objects(session).items()}
        tile = _objects(session)["p9b20"]

        # WHEN
        error = session.check_directive_value(tile, "for", {"id": [1, 20]})

        # THEN
        assert "p9b1 of common/parts/tile.jsonl:2 (id=1) is also the id of" in error
        with pytest.raises(InvalidDirectiveError, match="p9b2 of common/parts/tile.jsonl:3"):
            session.set_directive_value(tile, "for", {"id": [1, 20]})
        assert {name: dict(obj) for name, obj in _objects(session).items()} == before
        assert session.undo_description is None
        assert session.is_dirty is False

    @pytest.mark.parametrize(
        "key, value, error",
        [
            ("for", {"id": "{{ range(2000) }}"}, "'for' of 'id' has 2000 values, more than 1000"),
            ("vars", {"anchor": "{{ nope + 1 }}"}, "Can't render 'anchor'"),
            ("vars", {"id": 3}, "id is in 'vars' and in 'for': use one of them"),
        ],
    )
    def test_an_edit_with_an_error_is_refused(self, session, key, value, error):
        tile = _objects(session)["p9b20"]

        assert error in session.check_directive_value(tile, key, value)

    def test_a_template_value_is_rendered_with_the_including_file(self, session):
        # WHEN
        session.set_directive_value(_objects(session)["p9b20"], "for", {"id": "{{ [20, 25] }}"})

        # THEN
        assert {"p9b25", "p9b26"} <= set(_objects(session))

    def test_names_can_be_added_and_the_last_one_removes_the_key(self, cfg_root):
        # GIVEN
        _write_page(
            cfg_root,
            DIRECTIVE_PAGE_JSONL.replace('"vars": {"anchor": 1}', '"vars": {"note": "x"}').replace(
                '"for": {"id": [20, 30]}', '"for": {"id": [20, 30], "anchor": [1]}'
            ),
        )
        session = load_session(cfg_root)
        changes = []
        session.add_listener(changes.append)

        # WHEN: a name is added to the for
        session.set_directive_value(_objects(session)["p9b20"], "for", {"id": [20, 30], "anchor": [1], "row": [0]})

        # THEN: the instances are new, the object of the instance with the same id is selected
        tile = _objects(session)["p9b20"]
        assert changes[-1].selected == [tile]

        # WHEN: the last name of the vars is removed
        session.set_directive_value(tile, "vars", {})

        # THEN
        assert session.directive_of(tile) == {
            "!include": "common/parts/tile.jsonl",
            "for": {"id": [20, 30], "anchor": [1], "row": [0]},
        }
        assert session.origin_of(tile).includes[0].loop == {"id": 20, "anchor": 1, "row": 0}
        [change] = plan_save(session)
        directive = (
            '  // the tiles\n  "!include": "common/parts/tile.jsonl",\n  "for": {"id": [20, 30], "anchor": [1], "row": [0]}\n}'
        )
        assert directive in change.content

        # WHEN
        session.undo()

        # THEN
        assert session.directive_of(tile)["vars"] == {"note": "x"}
        [change] = plan_save(session)
        assert '"vars": {"note": "x"},' in change.content

    def test_after_a_save_the_directive_has_its_new_place(self, session, cfg_root):
        # GIVEN: an object before the directive is removed and saved
        tile = _objects(session)["p9b20"]
        session.remove_object(_objects(session)["p9b1"])
        [change] = plan_save(session)
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # WHEN
        session.set_directive_value(tile, "vars", {"anchor": 2})
        [change] = plan_save(session)

        # THEN
        assert session.line_of(tile) == 3 and session.origin_of(tile).includes[0].line == 3
        assert '"vars": {"anchor": 2}' in change.content
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # WHEN: undoing the var edit and the removal from before the saves
        session.undo()
        session.undo()

        # THEN
        assert session.origin_of(tile).includes[0].line == 3
        [change] = plan_save(session)
        assert '"vars": {"anchor": 1}' in change.content
        assert change.content.endswith('{"page": 9, "id": 1, "obj": "obj", "y": 10, "h": 20}\n')

    def test_an_object_added_after_a_directive_that_includes_nothing(self, cfg_root):
        # GIVEN: the directive is at the start of the file, and the draft has its objects in another order
        _write_page(cfg_root, '{"!include": "common/parts/nope.jsonl"}\n{"page": 9, "id": 1, "obj": "obj"}\n')
        session = load_session(cfg_root)
        [component] = session.components

        # WHEN: the draft writes the directive after the new object, the expansion finds its line (it raised an IndexError)
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "label", "text": "{{ p9b1.x }}"})
        session.set_source_value(_objects(session)["p9b1"], "x", 4)

        # THEN
        assert _objects(session)["p9b3"]["text"] == "4"
