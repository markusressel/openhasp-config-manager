from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

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
                value = self.variables[value.strip("{} ")]
            result[key] = value
        result.setdefault("bg_color", "#THEME")
        return result

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
        FakeRenderer({"left": 10, "right": 400}),
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
