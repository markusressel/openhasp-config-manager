from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.draft.files import SaveConflictError, load_device, load_part_alone, plan_save
from openhasp_config_manager.gui.domain.draft.part_alone import placeholder_vars
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.part_ids import new_part_object_ids
from openhasp_config_manager.gui.domain.draft.session import PlateSession, ReadOnlyObjectError
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.processing.jsonl.includes import IncludeLookupError
from openhasp_config_manager.processing.template_rendering import TemplateRenderError
from tests.helpers import copy_test_config, create_config_manager, load_session, write_page

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
    root = copy_test_config(tmp_path, {"common/parts/tile.jsonl": TILE_JSONL})
    write_page(root, PAGE_JSONL, "page.jsonl")
    return root


@pytest.fixture
def tile(cfg_root) -> Path:
    return cfg_root / "common" / "parts" / "tile.jsonl"


@pytest.fixture
def session(cfg_root) -> PlateSession:
    return load_session(cfg_root)


def _objects(session: PlateSession):
    return {object_name(obj): obj for objects in session.working_objects.values() for obj in objects}


def _edit_the_part(session: PlateSession, name: str = "p9b20"):
    return PartFocus(session, session.instance_of(_objects(session)[name]))


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
        focus = _edit_the_part(session)

        # THEN
        assert focus.instance.part == tile
        assert focus.read_only_reason(objects["p9b20"]) is None
        assert [name for name, obj in objects.items() if focus.is_selectable(obj)] == ["p9b20", "p9b21"]
        assert focus.read_only_reason(objects["p9b30"]) == (
            "In part mode only the objects of the part common/parts/tile.jsonl (of the instance that is shown) can be changed."
        )
        with pytest.raises(ReadOnlyObjectError):
            focus.set_source_value(objects["p9b1"], "x", 3)

    def test_two_views_of_the_draft_can_be_in_different_modes_at_once(self, session, tile):
        # GIVEN: one view edits the part in its first instance, another one in its third, and one the pages
        first = _edit_the_part(session)
        third = PartFocus(session, session.part_instances(tile)[2])
        objects = _objects(session)

        # THEN: each can change only its own objects
        assert [name for name, obj in objects.items() if first.read_only_reason(obj) is None] == ["p9b20", "p9b21"]
        assert [name for name, obj in objects.items() if third.read_only_reason(obj) is None] == ["p8b50", "p8b51"]
        assert [name for name, obj in objects.items() if session.read_only_reason(obj) is None] == ["p9b1", "p9b2"]
        assert all(session.is_selectable(obj) for obj in objects.values())
        with pytest.raises(ReadOnlyObjectError):
            session.set_source_value(objects["p9b21"], "text", "w")
        with pytest.raises(ReadOnlyObjectError):
            first.set_source_value(objects["p9b1"], "x", 3)

        # WHEN
        third.set_source_value(objects["p8b51"], "text", "w")
        session.set_source_value(objects["p9b1"], "x", 3)

        # THEN: every instance follows, and the modes stay
        assert [objects[name]["text"] for name in ("p9b21", "p9b31", "p8b51")] == ["w", "w", "w"]
        assert objects["p9b1"]["x"] == 3
        assert (first.instance, third.instance) == (session.part_instances(tile)[0], session.part_instances(tile)[2])

        # WHEN
        first.close()

        # THEN
        assert first.instance is None and third.read_only_reason(objects["p8b51"]) is None

    def test_an_edit_of_a_part_object_changes_every_instance_and_saves_only_the_part(self, session, tile):
        # GIVEN
        focus = _edit_the_part(session)
        objects = _objects(session)

        # WHEN
        focus.set_source_value(objects["p9b20"], "x", "{{ id * 3 }}")
        focus.set_source_value(objects["p9b21"], "text", "w")

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
        focus = _edit_the_part(session)

        # WHEN: like a drag
        with session.edit("Move p9b21"):
            focus.set_source_value(_objects(session)["p9b21"], "x", 7)
            focus.set_source_value(_objects(session)["p9b21"], "y", 8)

        # THEN
        objects = _objects(session)
        assert [(objects[name]["x"], objects[name]["y"]) for name in ("p9b21", "p9b31", "p8b51")] == [(7, 8)] * 3
        # p9b2 refers to p8b51
        assert objects["p9b2"]["x"] == 9
        assert session.undo_description == "Move p9b21"

    def test_adding_and_removing_objects_of_a_part(self, session, tile):
        # GIVEN
        focus = _edit_the_part(session)
        changes = []
        session.add_listener(changes.append)

        # WHEN
        added = focus.add_object(str(tile), {"page": 9, "id": 99, "obj": "btn", "x": 1})

        # THEN: in every instance, with templates for the page and id
        assert object_name(added) == "p9b22"
        assert session.source_of(added) == {"page": "{{ page }}", "id": "{{ id + 2 }}", "obj": "btn", "x": 1}
        assert {"p9b22", "p9b32", "p8b52"} <= set(_objects(session))
        assert changes[-1].selected == [added]
        assert focus.is_selectable(added)

        # WHEN
        focus.remove_object(_objects(session)["p9b21"])

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
        focus = _edit_the_part(session)

        # WHEN
        duplicate = focus.duplicate_object(_objects(session)["p9b21"])

        # THEN
        assert session.source_of(duplicate)["id"] == "{{ id + 2 }}"
        assert (duplicate["x"], duplicate["y"]) == (15, 50)

    def test_pasting_into_a_part_gives_the_objects_templates_and_every_instance_follows(self, session, tile):
        # GIVEN: a button with a label inside of it
        focus = _edit_the_part(session)
        clipboard = [
            {"page": 3, "id": 7, "obj": "btn", "x": 100, "y": 100, "w": 50, "h": 20},
            {"page": 3, "id": 8, "obj": "label", "parentid": 7, "text": "{{ id }}"},
        ]

        # WHEN: where the mouse is
        button, label = focus.paste_objects(str(tile), clipboard, page=9, screen=(480, 480), position=(60, 70))

        # THEN: with the page and the next ids of the part, the label still in the button
        assert session.source_of(button) == {
            "page": "{{ page }}",
            "id": "{{ id + 2 }}",
            "obj": "btn",
            "x": 60,
            "y": 70,
            "w": 50,
            "h": 20,
        }
        assert session.source_of(label) == {
            "page": "{{ page }}",
            "id": "{{ id + 3 }}",
            "obj": "label",
            "parentid": "{{ id + 2 }}",
            "text": "{{ id }}",
        }
        objects = _objects(session)
        assert (objects["p9b33"]["parentid"], objects["p9b33"]["text"], objects["p8b53"]["text"]) == (32, "30", "50")
        assert session.undo_description == "Paste 2 objects into the part"

        # WHEN
        [change] = plan_save(session)

        # THEN
        assert change.path == tile
        assert change.content.endswith(
            '{"page": "{{ page }}", "id": "{{ id + 2 }}", "obj": "btn", "x": 60, "y": 70, "w": 50, "h": 20}\n'
            '{"page": "{{ page }}", "id": "{{ id + 3 }}", "obj": "label", "parentid": "{{ id + 2 }}", "text": "{{ id }}"}\n'
        )

        # WHEN
        session.undo()

        # THEN
        assert not {"p9b22", "p9b32", "p8b53"} & set(_objects(session))
        assert session.is_dirty is False

    def test_pasting_into_a_part_needs_part_mode(self, session, tile):
        with pytest.raises(ReadOnlyObjectError):
            session.paste_objects(str(tile), [{"page": 9, "id": 3, "obj": "btn"}], page=9, screen=(480, 480))

    def test_leaving_part_mode_keeps_the_changes_and_switching_the_instance_too(self, session, tile):
        # GIVEN
        focus = _edit_the_part(session)
        focus.set_source_value(_objects(session)["p9b21"], "text", "w")

        # WHEN
        focus.close()
        focus = PartFocus(session, session.part_instances(tile)[2])

        # THEN
        objects = _objects(session)
        assert objects["p8b51"]["text"] == "w"
        assert focus.read_only_reason(objects["p8b51"]) is None and focus.read_only_reason(objects["p9b21"]) is not None

        # WHEN
        focus.close()

        # THEN
        assert focus.instance is None
        assert session.is_dirty is True and objects["p9b21"]["text"] == "w"
        assert session.read_only_reason(objects["p9b21"]).startswith("It is included from")

    def test_a_reload_that_can_not_be_rendered_keeps_part_mode_and_the_changes_of_the_part(self, session, tile, monkeypatch):
        # GIVEN: a change of the part in part mode
        focus = _edit_the_part(session)
        mode = focus.instance
        focus.set_source_value(_objects(session)["p9b21"], "text", "w")
        objects = _objects(session)

        def fail(path):
            raise TemplateRenderError("Unknown variable 'nope'")

        monkeypatch.setattr(session._renderer, "part_source", fail)

        # WHEN
        with pytest.raises(TemplateRenderError):
            session.reset_to_disk()

        # THEN: nothing changed, and the renderer has the parts of the draft again
        assert focus.instance == mode
        assert _objects(session) == objects and all(_objects(session)[name] is obj for name, obj in objects.items())
        assert [change.component.path for change in session.changes()] == [tile]
        focus.set_source_value(objects["p9b20"], "y", 11)
        assert (objects["p9b31"]["text"], objects["p8b50"]["y"]) == ("w", 11)

    def test_a_part_that_changed_on_disk_is_not_overwritten(self, session, tile):
        # GIVEN
        focus = _edit_the_part(session)
        focus.set_source_value(_objects(session)["p9b21"], "text", "w")
        tile.write_text(TILE_JSONL + "\n")

        # THEN
        with pytest.raises(SaveConflictError, match="tile.jsonl changed on disk"):
            plan_save(session)

    def test_after_a_save_the_part_goes_on_from_its_new_content(self, session, tile):
        # GIVEN: an object of the part is removed and saved
        focus = _edit_the_part(session)
        focus.remove_object(_objects(session)["p9b20"])
        [change] = plan_save(session)
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # THEN
        assert session.is_dirty is False
        assert session.origin_of(_objects(session)["p9b31"]).line == 2

        # WHEN: another change is saved, then both are undone
        focus.set_source_value(_objects(session)["p9b21"], "text", "w")
        [change] = plan_save(session)
        assert change.content.endswith('"text": "w"}\n')
        session.undo()
        session.undo()

        # THEN: the removed object comes back at the end of the part
        assert {"p9b20", "p9b30", "p8b50"} <= set(_objects(session))
        [change] = plan_save(session)
        assert change.content.endswith('"x": "{{ id * 2 }}", "y": 10, "text": "{{ id }}"}\n')

    def test_undoing_past_a_save_shows_the_saved_lines_of_the_part(self, session, tile):
        # GIVEN: the first object of the part is removed and saved, which moves the second one to line 2
        focus = _edit_the_part(session)
        focus.remove_object(_objects(session)["p9b20"])
        [change] = plan_save(session)
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # WHEN
        session.undo()

        # THEN: the removed object is new in the draft, the other one stays where the file has it now
        objects = _objects(session)
        assert session.origin_of(objects["p9b21"]).line == 2
        assert session.origin_of(objects["p9b20"]).line is None

    def test_a_directive_after_a_saved_removal_keeps_its_part_mode(self, session, cfg_root):
        # GIVEN: the object before the directives is removed, then part mode is entered and the file saved
        instance = session.instance_of(_objects(session)["p9b30"])
        session.remove_object(_objects(session)["p9b1"])
        focus = PartFocus(session, instance)
        [change] = plan_save(session)
        change.path.write_text(change.content)

        # WHEN
        session.mark_saved({change.path: change.content})

        # THEN: the directive is the first object of the file now
        assert focus.instance in session.part_instances(instance.part)
        assert session.describe_instance(focus.instance) == f"{DEVICE}/page.jsonl:1 (id=30)"
        assert focus.read_only_reason(_objects(session)["p9b30"]) is None

    def test_a_page_file_cant_be_edited_as_a_part(self, cfg_root):
        # GIVEN: a page file that is also included
        (cfg_root / DEVICE / "other.jsonl").write_text('{"page": 7, "id": 1, "obj": "obj"}\n')
        (cfg_root / DEVICE / "page.jsonl").write_text(f'{{"!include": "{DEVICE}/other.jsonl", "vars": {{"x": 1}}}}\n')
        (cfg_root / DEVICE / "boot.cmd").write_text("run L:/page.jsonl\nrun L:/other.jsonl\n")
        session = load_session(cfg_root)
        [included] = session.working_objects[str(cfg_root / DEVICE / "page.jsonl")]

        # THEN
        with pytest.raises(ValueError, match="is also a page file of the device"):
            PartFocus(session, session.instance_of(included))


class TestPartTab:
    """A part tab undoes, and marks as unsaved, the part and the file that includes its instance (`PartFocus.undo_scope`)."""

    @pytest.fixture
    def cfg_root(self, cfg_root) -> Path:
        # another file of the device, which the part tab doesn't show
        (cfg_root / DEVICE / "other.jsonl").write_text('{"page": 2, "id": 5, "obj": "obj", "x": 1}\n')
        (cfg_root / DEVICE / "boot.cmd").write_text("run L:/page.jsonl\nrun L:/other.jsonl\n")
        return cfg_root

    def test_undo_and_unsaved_changes_of_the_part_and_its_file(self, session, tile, cfg_root):
        # GIVEN: an edit of the other file, then one of the part
        session.set_source_value(_objects(session)["p2b5"], "x", 2)
        focus = _edit_the_part(session)
        assert focus.undo_scope == {str(tile), str(cfg_root / DEVICE / "page.jsonl")}
        assert not focus.is_dirty and focus.next_undo is None
        focus.set_source_value(_objects(session)["p9b20"], "y", 11)

        # THEN
        assert focus.is_dirty and focus.next_undo.description == "Change y of p9b20"

        # WHEN
        focus.undo()

        # THEN: only the part changed back; the draft of the device undoes the edit of the other file next
        assert _objects(session)["p9b20"]["y"] == 10 and _objects(session)["p2b5"]["x"] == 2
        assert not focus.is_dirty and focus.next_undo is None
        assert session.next_undo.description == "Change x of p2b5"

        # WHEN
        focus.redo()

        # THEN
        assert _objects(session)["p9b20"]["y"] == 11

    def test_a_reload_goes_on_in_the_instance_at_the_same_place(self, session, tile, cfg_root):
        # GIVEN
        focus = PartFocus(session, session.part_instances(tile)[1])
        page = cfg_root / DEVICE / "page.jsonl"

        # WHEN: the file that includes it changed on disk, the instances stay where they are
        page.write_text(PAGE_JSONL.replace('"y": 10', '"y": 12'))
        loaded = load_device(create_config_manager(cfg_root), "test_device")
        session.load(loaded.components, loaded.renderer)

        # THEN
        assert session.describe_instance(focus.instance) == f"{DEVICE}/page.jsonl:2 (id=30)"

        # WHEN: it doesn't include the part anymore
        page.write_text(PAGE_JSONL.splitlines()[0] + "\n")
        loaded = load_device(create_config_manager(cfg_root), "test_device")
        session.load(loaded.components, loaded.renderer)

        # THEN
        assert focus.instance is None and not focus.is_active


class TestNestedParts:
    @pytest.fixture
    def session(self, cfg_root) -> PlateSession:
        (cfg_root / "common" / "parts" / "tile.jsonl").write_text(TILE_JSONL + NESTED_JSONL.split("\n", 1)[1])
        (cfg_root / "common" / "parts" / "dot.jsonl").write_text(DOT_JSONL)
        return load_session(cfg_root)

    def test_the_objects_of_an_inner_part_are_selectable_but_not_editable(self, session, cfg_root):
        # GIVEN
        focus = _edit_the_part(session)
        dot = _objects(session)["p9b26"]

        # THEN
        assert focus.is_selectable(dot)
        assert focus.read_only_reason(dot) == (
            "It is included from common/parts/dot.jsonl:1, by an !include inside of the part common/parts/tile.jsonl: "
            "edit that part."
        )
        inner = session.instance_of(dot)
        assert inner.part == cfg_root / "common/parts/dot.jsonl"
        assert session.instance_of(dot, cfg_root / "common/parts/tile.jsonl") == focus.instance

    def test_an_edit_of_the_inner_part_changes_its_instances_in_every_outer_instance(self, session):
        # GIVEN
        focus = PartFocus(session, session.instance_of(_objects(session)["p9b26"]))

        # WHEN
        focus.set_source_value(_objects(session)["p9b26"], "x", 9)

        # THEN
        objects = _objects(session)
        assert [objects[name]["x"] for name in ("p9b26", "p9b36", "p8b56")] == [9, 9, 9]
        assert [change.component.path.name for change in session.changes()] == ["dot.jsonl"]

    def test_undoing_past_a_save_shows_the_saved_line_of_an_inner_directive(self, session):
        # GIVEN: an object before the inner directive is removed and saved, which moves the directive to line 3
        focus = _edit_the_part(session)
        focus.remove_object(_objects(session)["p9b20"])
        [change] = plan_save(session)
        change.path.write_text(change.content)
        session.mark_saved({change.path: change.content})

        # WHEN
        session.undo()

        # THEN
        assert session.origin_of(_objects(session)["p9b26"]).includes[1].line == 3


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


class TestPartAlone:
    @pytest.fixture
    def card(self, cfg_root) -> Path:
        # no file of the device includes it; its folder has a default for the gap
        folder = cfg_root / "common" / "parts" / "card"
        folder.mkdir()
        (folder / "card.yaml").write_text("gap: 4\n")
        path = folder / "card.jsonl"
        path.write_text(
            '{"page": "{{ card.page }}", "id": "{{ card.id }}", "obj": "obj", "x": "{{ gap }}", "w": 100, "h": 50}\n'
            '{"page": "{{ card.page }}", "id": "{{ card.id + 1 }}", "obj": "label", "y": "{{ p1b1.h + 1 }}",'
            ' "text": "{{ title }}"}\n'
        )
        return path

    def _session(self, cfg_root: Path, part: Path) -> PlateSession:
        config_manager = create_config_manager(cfg_root)
        loaded = load_device(config_manager, "test_device")
        component, renderer = load_part_alone(config_manager, loaded.device, part)
        session = PlateSession(device=loaded.device)
        session.load([component], renderer)
        return session

    def test_a_part_alone_has_a_placeholder_for_each_variable_it_needs(self, cfg_root, card):
        # GIVEN: the pages of the device have a p1b1 too
        page = cfg_root / DEVICE / "page.jsonl"
        page.write_text(page.read_text() + '{"page": 1, "id": 1, "obj": "obj", "h": 999}\n')

        # WHEN
        session = self._session(cfg_root, card)

        # THEN: on its own, the object references see only its objects
        [component] = session.components
        assert component.is_scratch and session.is_part_alone
        assert component.sources == [
            {"!include": "common/parts/card/card.jsonl", "vars": {"card": {"page": 1, "id": 1}, "title": 1}}
        ]
        objects = _objects(session)
        assert list(objects) == ["p1b1", "p1b2"]
        assert (objects["p1b1"]["x"], objects["p1b2"]["y"], objects["p1b2"]["text"]) == (4, 51, "1")
        assert session.is_dirty is False

    def test_edits_and_vars_of_a_part_alone_save_only_the_part(self, cfg_root, card):
        # GIVEN
        session = self._session(cfg_root, card)
        [instance] = session.part_instances(card)
        focus = PartFocus(session, instance)
        label = _objects(session)["p1b2"]

        # WHEN: the vars are no change of a file
        session.set_directive_value(label, "vars", {"card": {"page": 2, "id": 10}, "title": "Lights"})

        # THEN
        assert set(_objects(session)) == {"p2b10", "p2b11"}
        assert label["text"] == "Lights"
        assert session.is_dirty is False
        assert focus.instance == instance

        # WHEN
        focus.set_source_value(label, "text", "{{ title }}!")

        # THEN
        [change] = plan_save(session)
        assert change.path == card
        assert '"text": "{{ title }}!"' in change.content
        session.mark_saved({change.path: change.content})
        assert session.is_dirty is False
        assert label["text"] == "Lights!"

    def test_a_part_alone_must_be_a_file_of_the_device(self, cfg_root):
        # GIVEN
        other = cfg_root / "devices" / "other.jsonl"
        other.write_text("{}\n")
        config_manager = create_config_manager(cfg_root)
        loaded = load_device(config_manager, "test_device")

        # THEN
        with pytest.raises(IncludeLookupError):
            load_part_alone(config_manager, loaded.device, other)


class TestPlaceholderVars:
    def test_the_variables_a_part_needs(self):
        sources = [
            {"page": "{{ page }}", "id": "{{ ids.base + 1 }}", "x": "{{ b{{ anchor }}.x + this.w }}", "y": "{{ p1b2.y }}"},
            {"text": "{% for i in range(n) %}{{ i }}{% endfor %} {{ known.size }}"},
            {"!include": "common/parts/dot.jsonl", "vars": {"x": "{{ dot * 2 + offset }}"}, "for": {"dot": [1, 2]}},
        ]

        # THEN: not those of the folders, the objects, the loops of templates and of !include
        assert placeholder_vars(sources, {"known": {"size": 3}}) == {
            "page": 1,
            "ids": {"base": 1},
            "anchor": 1,
            "n": 1,
            "offset": 1,
        }

    def test_a_value_that_the_defaults_of_a_mapping_dont_have(self):
        sources = [{"id": "{{ tile.id }}", "x": "{{ tile.column * 10 }}", "text": "{{ device.name }}"}]

        # THEN: merged into the mapping of the defaults; what is no mapping may have anything
        assert placeholder_vars(sources, {"tile": {"column": 0}, "device": object()}) == {"tile": {"id": 1}}
