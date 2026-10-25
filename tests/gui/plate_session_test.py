from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from jinja2 import TemplateSyntaxError

from openhasp_config_manager.gui.domain.plate_session import ComponentSource, PlateSession
from tests import TestBase


class FakeRenderer:
    """Renders "{{ name }}" templates from a dict, and adds a theme default like ObjectThemeProcessor."""

    def __init__(self, variables: Dict[str, Any]):
        self.variables = variables

    def render_object(self, component: str, source: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, value in source.items():
            if isinstance(value, str) and value.startswith("{{"):
                name = value.strip("{} ")
                if name not in self.variables:
                    raise TemplateSyntaxError(f"broken: {value}", 1)
                value = self.variables[name]
            result[key] = value
        result.setdefault("bg_color", "#THEME")
        return result

    def set_draft_sources(self, sources: Dict[str, List[Dict[str, Any]]]):
        pass

    def check_template(self, component: str, template: str) -> Optional[str]:
        return None if template.strip("{} ") in self.variables else "Unknown variable"

    def template_suggestions(self, component: str) -> List[Tuple[str, Any]]:
        return [(f"{{{{ {name} }}}}", value) for name, value in self.variables.items()]


def _session() -> PlateSession:
    session = PlateSession(device=None)
    session.load(
        [
            ComponentSource(
                key="a.jsonl",
                path=Path("a.jsonl"),
                content="",
                is_common=False,
                sources=[
                    {"page": 1, "id": 1, "obj": "btn", "x": "{{ left }}", "text": "A"},
                    {"page": 1, "id": 2, "obj": "label", "text": "B", "y": "15%"},
                ],
            ),
            ComponentSource(key="b.jsonl", path=Path("b.jsonl"), content="", is_common=True, sources=[]),
        ],
        FakeRenderer({"left": 10, "right": 400, "name": "Markus"}),
    )
    return session


class TestPlateSession(TestBase):
    def test_not_loaded_before_load(self):
        assert PlateSession(device=None).is_loaded is False

    def test_load_renders_the_sources(self):
        # WHEN
        session = _session()

        # THEN
        button = session.working_objects["a.jsonl"][0]
        assert button["x"] == 10
        assert button["bg_color"] == "#THEME"
        assert session.source_of(button)["x"] == "{{ left }}"
        assert session.is_template(button, "x") is True
        assert session.is_template(button, "text") is False
        label = session.working_objects["a.jsonl"][1]
        assert session.is_percentage(label, "y") is True
        assert session.is_percentage(button, "x") is False
        assert session.is_loaded is True
        assert session.is_dirty is False
        assert session.changes() == []

    def test_where_objects_are_written(self, tmp_path):
        # GIVEN
        path = tmp_path / "a.jsonl"
        content = '// two objects\n{"page": 1, "id": 1}\n\n{\n  "page": 1, "id": 2\n}\n'
        session = PlateSession(device=None)
        session.load(
            [ComponentSource("a.jsonl", path, content, False, [{"page": 1, "id": 1}, {"page": 1, "id": 2}])],
            FakeRenderer({}),
        )
        first, second = session.working_objects["a.jsonl"]

        # WHEN
        added = session.add_object("a.jsonl", {"page": 1, "id": 3, "obj": "btn"})

        # THEN
        assert (session.line_of(first), session.line_of(second), session.line_of(added)) == (2, 4, None)
        assert session.component_at(tmp_path / "." / "a.jsonl").key == "a.jsonl"
        assert session.component_at(tmp_path / "b.jsonl") is None

    def test_set_a_value_renders_into_the_same_object(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # WHEN
        session.set_source_value(label, "text", "C")

        # THEN
        assert label is session.working_objects["a.jsonl"][1]
        assert label["text"] == "C"
        assert session.is_dirty is True
        [changes] = session.changes()
        assert changes.changes == {1: {"text": "C"}}

    def test_set_a_template(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # WHEN
        session.set_source_value(label, "x", "{{ right }}")

        # THEN
        assert label["x"] == 400
        assert session.changes()[0].changes == {1: {"x": "{{ right }}"}}

    def test_changing_a_theme_default_writes_it_and_removing_it_restores_the_default(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # WHEN
        session.set_source_value(label, "bg_color", "#FF0000")

        # THEN
        assert session.changes()[0].changes == {1: {"bg_color": "#FF0000"}}

        # WHEN
        session.remove_source_value(label, "bg_color")

        # THEN
        assert label["bg_color"] == "#THEME"
        assert session.changes() == []

    def test_computed_position_reasons_name_the_properties_and_their_values(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]
        session.set_source_value(button, "y", "{{ right }}")

        # WHEN
        result = [session.computed_position_reasons(obj, max_length=10) for obj in (button, label)]

        # THEN
        assert result == [
            ["x is a template: {{ left }}", "y is a template: {{ right …"],
            ["y is a percentage: 15%"],
        ]

    def test_use_pixel_position_replaces_a_computed_position_with_its_pixels(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]

        # WHEN
        session.use_pixel_position(button)

        # THEN
        assert session.source_of(button)["x"] == 10
        assert session.has_computed_position(button) is False
        assert session.has_computed_position(label) is True
        assert session.is_dirty

    def test_paste_gives_new_ids_and_keeps_the_layout_and_templates(self):
        # GIVEN
        session = _session()
        sources = [
            {"page": 7, "id": 1, "obj": "obj", "x": 100, "y": 50, "w": 50, "h": 20, "text": "{{ name }}"},
            {"page": 7, "id": 2, "obj": "btn", "x": 5, "y": 5, "parentid": 1},
            {"page": 7, "id": 3, "obj": "label", "x": 120, "y": 80, "w": 10, "h": 10, "parentid": 99},
        ]

        # WHEN
        pasted = session.paste_objects("b.jsonl", sources, page=1, screen=(480, 320), position=(20, 30), offset=10)

        # THEN
        # ids 1 and 2 are used on page 1
        assert [(obj["page"], obj["id"]) for obj in pasted] == [(1, 3), (1, 4), (1, 5)]
        assert (pasted[0]["x"], pasted[0]["y"]) == (30, 40)
        # inside of its pasted parent: unchanged, relative to it
        assert (pasted[1]["parentid"], pasted[1]["x"]) == (3, 5)
        # its parent isn't pasted
        assert "parentid" not in pasted[2]
        assert (pasted[2]["x"], pasted[2]["y"]) == (50, 70)
        assert session.source_of(pasted[0])["text"] == "{{ name }}"
        assert pasted == session.working_objects["b.jsonl"]
        assert sources[0]["id"] == 1

    def test_paste_without_a_position_moves_from_the_originals_and_stays_on_the_screen(self):
        # GIVEN
        session = _session()
        source = {"page": 1, "id": 1, "obj": "btn", "x": 400, "y": 10, "w": 60, "h": 20}

        # WHEN
        pasted = session.paste_objects("b.jsonl", [source], page=1, screen=(480, 320), offset=30)

        # THEN
        assert (pasted[0]["x"], pasted[0]["y"]) == (420, 40)

    def test_paste_adds_nothing_if_an_object_cant_be_rendered(self):
        # GIVEN
        session = _session()

        # WHEN
        with pytest.raises(TemplateSyntaxError):
            session.paste_objects(
                "b.jsonl", [{"obj": "btn"}, {"obj": "label", "text": "{{ unknown }}"}], page=1, screen=(480, 320)
            )

        # THEN
        assert session.working_objects["b.jsonl"] == []
        assert session.is_dirty is False

    def test_add_duplicate_and_remove(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]

        # WHEN
        added = session.add_object("b.jsonl", {"page": 1, "id": 3, "obj": "label"})
        duplicate = session.duplicate_object(button)
        session.remove_object(label)

        # THEN
        assert added in session.working_objects["b.jsonl"]
        # ids 1, 2 and 3 are used on page 1 when it is duplicated
        assert (duplicate["id"], duplicate["x"]) == (4, 20)
        changes = {c.component.key: c for c in session.changes()}
        assert changes["a.jsonl"].deletions == {1}
        assert changes["a.jsonl"].additions == [{"page": 1, "id": 4, "obj": "btn", "x": 20, "y": 10, "text": "A"}]
        assert changes["a.jsonl"].expected_sources == [
            {"page": 1, "id": 1, "obj": "btn", "x": "{{ left }}", "text": "A"},
            {"page": 1, "id": 4, "obj": "btn", "x": 20, "y": 10, "text": "A"},
        ]
        assert changes["b.jsonl"].additions == [{"page": 1, "id": 3, "obj": "label"}]

    def test_reset_to_disk_discards_changes(self):
        # GIVEN
        session = _session()
        session.set_source_value(session.working_objects["a.jsonl"][1], "text", "C")
        session.add_object("b.jsonl", {"page": 1, "id": 3})

        # WHEN
        session.reset_to_disk()

        # THEN
        assert session.working_objects["a.jsonl"][1]["text"] == "B"
        assert session.working_objects["b.jsonl"] == []
        assert session.is_dirty is False
        assert session.changes() == []

    def test_removing_a_property_of_the_file_is_not_supported(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]
        session.remove_source_value(label, "text")

        # THEN
        with pytest.raises(AssertionError):
            session.changes()

    def test_template_checks_and_suggestions_use_the_component_of_the_object(self):
        # GIVEN
        session = _session()
        button = session.working_objects["a.jsonl"][0]

        # THEN
        assert session.check_template(button, "{{ left }}") is None
        assert session.check_template(button, "{{ nope }}") == "Unknown variable"
        assert ("{{ left }}", 10) in session.template_suggestions(button)

    def test_a_value_that_does_not_render_changes_nothing(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # WHEN
        with pytest.raises(TemplateSyntaxError):
            session.set_source_value(label, "text", "{{ broken")

        # THEN
        assert session.source_of(label)["text"] == "B"
        assert label["text"] == "B"
        assert session.is_dirty is False

    def test_check_value(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # THEN
        assert session.check_value(label, "x", "{{ left }}") is None
        assert session.check_value(label, "text", "{{ name }}") is None
        assert session.check_value(label, "text", "{{ broken") == "Invalid template: broken: {{ broken"
        assert session.check_value(label, "x", "{{ name }}") == "Must be a number, renders to 'Markus'."
        # only exact names of numeric properties, not e.g. "hidden" for "h"
        assert session.check_value(label, "hidden", "{{ name }}") is None
        # the check does not change the object
        assert label["text"] == "B" and session.is_dirty is False


class TestUndo(TestBase):
    def test_undo_and_redo_a_value_in_the_same_rendered_object(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]
        session.set_source_value(label, "text", "C")

        # WHEN
        undone = session.undo()

        # THEN the preview keeps showing the same dict
        assert label["text"] == "B"
        assert undone.description == "Change text of p1b2"
        assert undone.objects == [label] and undone.pages == {1}
        assert session.is_dirty is False

        # WHEN
        redone = session.redo()

        # THEN
        assert label["text"] == "C"
        assert session.source_of(label)["text"] == "C"
        assert redone.objects == [label]
        assert session.is_dirty is True

    def test_nothing_to_undo_or_redo(self):
        session = _session()
        assert session.undo() is None
        assert session.redo() is None

    def test_undo_a_removal_brings_the_object_back_in_its_place(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]
        session.remove_object(button)

        # WHEN
        restored = session.undo()

        # THEN
        [again] = restored.objects
        assert session.working_objects["a.jsonl"] == [again, label]
        assert again == button
        assert session.source_of(again)["x"] == "{{ left }}"
        assert session.source_index(again) == 0
        assert session.is_dirty is False
        assert session.changes() == []

    def test_undo_an_addition(self):
        # GIVEN
        session = _session()
        session.add_object("b.jsonl", {"page": 2, "id": 3, "obj": "label"})

        # WHEN
        restored = session.undo()

        # THEN
        assert session.working_objects["b.jsonl"] == []
        assert restored.objects == [] and restored.pages == {2}
        assert session.is_dirty is False

    def test_an_edit_groups_changes_into_one_step(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]

        # WHEN
        with session.edit("Move 2 objects"):
            session.set_source_value(button, "x", 50)
            session.set_source_value(label, "y", 60)

        # THEN
        assert session.history.undo_description == "Move 2 objects"
        session.undo()
        assert (button["x"], label["y"]) == (10, "15%")
        assert session.undo() is None

    def test_paste_and_duplicate_are_one_step_each(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]

        # WHEN
        session.paste_objects("b.jsonl", [session.source_of(button), session.source_of(button)], 1, (480, 320))
        session.duplicate_object(button)

        # THEN
        assert session.history.undo_description == "Duplicate p1b1"
        session.undo()
        assert session.history.undo_description == "Paste 2 objects"
        session.undo()
        assert session.working_objects["a.jsonl"] == [button, label]
        assert session.working_objects["b.jsonl"] == []

    def test_an_edit_that_changes_nothing_is_no_step(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]

        # WHEN
        session.set_source_value(label, "text", "B")

        # THEN
        assert session.undo() is None
        assert session.is_dirty is False

    def test_edits_with_a_merge_key_are_one_step(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]
        key = ("text", session.object_uid(label))

        # WHEN typing
        for text in ["B", "Bo", "Bob"]:
            with session.edit("Change text", merge_key=key):
                session.set_source_value(label, "text", text)

        # THEN
        session.undo()
        assert label["text"] == "B"
        assert session.undo() is None

    def test_changing_a_value_back_is_not_dirty(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]
        session.set_source_value(label, "text", "C")

        # WHEN
        session.set_source_value(label, "text", "B")

        # THEN
        assert session.is_dirty is False

    def test_the_uid_of_an_object_stays_after_undoing_its_removal(self):
        # GIVEN
        session = _session()
        label = session.working_objects["a.jsonl"][1]
        uid = session.object_uid(label)
        session.remove_object(label)

        # WHEN
        [again] = session.undo().objects

        # THEN
        assert session.object_uid(again) == uid

    def test_reset_to_disk_clears_the_history(self):
        # GIVEN
        session = _session()
        session.set_source_value(session.working_objects["a.jsonl"][1], "text", "C")

        # WHEN
        session.reset_to_disk()

        # THEN
        assert session.undo() is None

    def test_the_states_of_the_history_share_the_sources_that_did_not_change(self):
        # GIVEN
        session = _session()
        button, label = session.working_objects["a.jsonl"]
        before = session._state()

        # WHEN
        session.set_source_value(label, "text", "C")

        # THEN only the changed source is a new copy
        after = session._state()
        assert after["a.jsonl"][0][2] is before["a.jsonl"][0][2]
        assert after["a.jsonl"][1][2] is not before["a.jsonl"][1][2]
        assert before["a.jsonl"][1][2]["text"] == "B"
