import json
import textwrap
from pathlib import Path
from typing import Dict, List

import pytest

from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.device_processor import DeviceProcessor
from openhasp_config_manager.processing.jsonl.includes import (
    MAX_INSTANCES,
    IncludeExpansionError,
    IncludedObjectError,
    IncludeStep,
    describe_includes,
    directive_error,
    directive_paths,
    display_path,
    is_directive,
)
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase

TILE = textwrap.dedent("""
    {"page": "{{ page }}", "id": "{{ id }}", "obj": "label", "x": "{{ x }}", "y": "{{ y }}", "text": "{{ caption }}"}
    {"page": "{{ page }}", "id": "{{ id + 1 }}", "obj": "label", "x": "{{ x }}", "y": "{{ tile.value_y }}", "text": "-"}
    """)


class IncludeTestBase(TestBase):
    """A config directory in tmp_path with a device `plate`, whose .jsonl files are the components of a processor."""

    def setup_config(self, tmp_path: Path, files: Dict[str, str]) -> Dict[str, JsonlComponent]:
        (tmp_path / "common").mkdir(exist_ok=True)
        (tmp_path / "devices" / "plate").mkdir(parents=True, exist_ok=True)
        (tmp_path / "devices" / "other").mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(content).strip() + "\n")
        self.config_dir = tmp_path
        variable_manager = VariableManager(tmp_path)
        variable_manager.read()
        self.device = Device(
            name="plate",
            path=tmp_path / "devices" / "plate",
            config=self.default_config,
            cmd=[],
            jsonl=[],
            images=[],
            fonts=[],
            output_dir=None,
        )
        self.processor = DeviceProcessor(self.device, [ObjectDimensionsProcessor()], variable_manager)
        components = {}
        for name in files:
            # like the analysis: the files of the common folder and of the device
            if name.endswith(".jsonl") and not name.startswith("devices/other/"):
                path = tmp_path / name
                component = JsonlComponent(name=name.replace("/", "_"), type="jsonl", path=path, content=path.read_text())
                self.processor.add_component(component)
                components[name] = component
        return components

    def render(self, component: JsonlComponent) -> List[Dict]:
        return [json.loads(line) for line in self.processor.normalize(self.device, component).splitlines()]

    def errors(self, component: JsonlComponent) -> List[str]:
        return [error.message for error in self.processor.expand_jsonl_objects(component).errors]


class TestIncludes(IncludeTestBase):
    def test_the_objects_of_the_part_replace_the_directive(self, tmp_path):
        # GIVEN: the defaults of the part are next to it, `value_y` is computed from the parameter `y`
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/tile.jsonl": TILE,
                "common/parts/tile.vars.yaml": 'tile:\n  value_y: "{{ y + 22 }}"\n',
                "devices/plate/page.jsonl": """
                    {"page": 3, "id": 1, "obj": "obj"}
                    {"!include": "common/parts/tile.jsonl", "vars": {"page": 3, "id": 29, "x": 10, "y": 50, "caption": "Elapsed"}}
                    {"page": 3, "id": 2, "obj": "obj"}
                """,
            },
        )

        # WHEN
        result = self.render(components["devices/plate/page.jsonl"])

        # THEN
        assert [(obj["id"], obj.get("y")) for obj in result] == [(1, None), (29, 50), (30, 72), (2, None)]
        assert result[1]["text"] == "Elapsed"

    def test_for_includes_the_part_for_every_combination_of_the_values(self, tmp_path):
        # GIVEN: the first key changes slowest, `vars` see the loop variables, the values can be a template
        components = self.setup_config(
            tmp_path,
            {
                "global.vars.yaml": "pages: [1, 2]\n",
                "common/parts/dot.jsonl": '{"page": "{{ page }}", "id": "{{ id }}", "x": "{{ dot * 10 }}"}',
                "devices/plate/page.jsonl": """
                    {
                      "!include": "common/parts/dot.jsonl",
                      "vars": {"id": "{{ 100 + dot }}"},
                      "for": {"page": "{{ pages }}", "dot": [0, 1, 2]}
                    }
                """,
            },
        )

        # WHEN
        result = self.render(components["devices/plate/page.jsonl"])

        # THEN
        assert [(obj["page"], obj["id"], obj["x"]) for obj in result] == [
            (1, 100, 0),
            (1, 101, 10),
            (1, 102, 20),
            (2, 100, 0),
            (2, 101, 10),
            (2, 102, 20),
        ]

    def test_for_with_a_range(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ dot }}"}',
                "devices/plate/page.jsonl": '{"!include": "common/parts/dot.jsonl", "for": {"dot": "{{ range(1, 4) }}"}}',
            },
        )

        assert [obj["id"] for obj in self.render(components["devices/plate/page.jsonl"])] == [1, 2, 3]

    def test_the_including_scope_wins_over_the_defaults_of_the_part(self, tmp_path):
        # GIVEN: the device overrides a default of the part and a global variable the default uses
        components = self.setup_config(
            tmp_path,
            {
                "global.vars.yaml": "margin: 4\n",
                "common/parts/box.jsonl": '{"page": 1, "id": "{{ id }}", "x": "{{ box.x }}", "h": "{{ box.h }}"}',
                "common/parts/box.vars.yaml": 'box:\n  x: "{{ margin * 2 }}"\n  h: 10\n',
                "devices/plate/vars.yaml": "margin: 6\nbox:\n  h: 30\n",
                "devices/plate/page.jsonl": '{"!include": "common/parts/box.jsonl", "vars": {"id": 5}}',
            },
        )

        # THEN: the default `x` is computed with the device's `margin`
        assert self.render(components["devices/plate/page.jsonl"]) == [{"page": 1, "id": 5, "x": 12, "h": 30}]

    def test_vars_win_over_the_including_scope_and_for_over_vars(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "devices/plate/vars.yaml": "label:\n  text: device\n  size: 12\n",
                "common/parts/label.jsonl": '{"page": 1, "id": "{{ id }}", "text": "{{ label.text }} {{ label.size }}"}',
                "devices/plate/page.jsonl": '{"!include": "common/parts/label.jsonl", "vars": {"label": {"text": "vars"}}, "for": {"id": [1]}}',
            },
        )

        # THEN: mappings are merged deeply
        assert self.render(components["devices/plate/page.jsonl"]) == [{"page": 1, "id": 1, "text": "vars 12"}]

    def test_a_part_can_include_a_part_with_its_parameters(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ id }}", "text": "{{ caption }}"}',
                "common/parts/row.jsonl": """
                    {"!include": "common/parts/dot.jsonl", "vars": {"id": "{{ first }}"}}
                    {"!include": "common/parts/dot.jsonl", "vars": {"id": "{{ first + 1 }}", "caption": "second"}}
                """,
                "devices/plate/page.jsonl": '{"!include": "common/parts/row.jsonl", "vars": {"first": 7, "caption": "first"}}',
            },
        )

        assert self.render(components["devices/plate/page.jsonl"]) == [
            {"page": 1, "id": 7, "text": "first"},
            {"page": 1, "id": 8, "text": "second"},
        ]

    def test_where_the_objects_come_from(self, tmp_path):
        # GIVEN
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '// a dot\n{"page": 1, "id": "{{ id }}"}',
                "common/parts/row.jsonl": '{"!include": "common/parts/dot.jsonl", "vars": {"id": "{{ first + i }}"}, "for": {"i": [0, 1]}}',
                "devices/plate/page.jsonl": '{"page": 1, "id": 1}\n\n{"!include": "common/parts/row.jsonl", "vars": {"first": 10}}',
            },
        )

        # WHEN
        expansion = self.processor.expand_jsonl_objects(components["devices/plate/page.jsonl"])

        # THEN
        assert expansion.errors == []
        plain, first, second = expansion.objects
        assert (plain.name, plain.origin.line, plain.origin.is_included) == (None, None, False)
        assert (first.name, second.name) == ("p1b10", "p1b11")
        assert (first.origin.file, first.origin.index, first.origin.line) == (tmp_path / "common/parts/dot.jsonl", 0, 2)
        outer, inner = second.origin.includes
        assert (outer.file, outer.index, outer.line, outer.vars, outer.loop) == (
            tmp_path / "devices/plate/page.jsonl",
            1,
            3,
            {"first": 10},
            {},
        )
        assert (inner.file, inner.line, inner.vars, inner.loop) == (
            tmp_path / "common/parts/row.jsonl",
            1,
            {"id": 11},
            {"i": 1},
        )
        assert second.scope["id"] == 11 and second.scope["first"] == 10
        assert describe_includes(second.origin.includes, tmp_path) == (
            "included at devices/plate/page.jsonl:3 > common/parts/row.jsonl:1 (i=1)"
        )


class TestReferences(IncludeTestBase):
    def test_included_objects_and_the_objects_of_the_file_refer_to_each_other(self, tmp_path):
        # GIVEN: the tile is placed below object 4 of the page, and object 5 is placed next to the tile
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/tile.jsonl": """
                    {"page": 2, "id": "{{ id }}", "y": "{{ b{{ anchor }}.y + b{{ anchor }}.h }}", "h": 20}
                    {"page": 2, "id": "{{ id + 1 }}", "y": "{{ b{{ id }}.y }}", "w": "{{ this.id * 2 }}"}
                """,
                "devices/plate/page.jsonl": """
                    {"page": 2, "id": 4, "y": 10, "h": "25%"}
                    {"!include": "common/parts/tile.jsonl", "vars": {"id": 20, "anchor": 4}}
                    {"page": 2, "id": 5, "y": "{{ p2b21.y + b20.h }}"}
                """,
            },
        )

        # WHEN
        result = self.render(components["devices/plate/page.jsonl"])

        # THEN: 25 % of 480 is 120
        assert result[1:] == [
            {"page": 2, "id": 20, "y": 130, "h": 20},
            {"page": 2, "id": 21, "y": 130, "w": 42},
            {"page": 2, "id": 5, "y": 150},
        ]

    def test_the_objects_of_a_part_count_through_its_instances_in_other_files(self, tmp_path):
        # GIVEN: the part has defaults, which are no object of the page on their own
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ id }}", "x": "{{ id * 2 }}"}',
                "common/parts/dot.vars.yaml": "id: 1\n",
                "devices/plate/dots.jsonl": '{"!include": "common/parts/dot.jsonl", "vars": {"id": 3}}',
                "devices/plate/page.jsonl": '{"page": 1, "id": 9, "x": "{{ b3.x }}", "text": "{{ b1 is defined }}"}',
            },
        )

        # THEN
        assert self.render(components["devices/plate/page.jsonl"]) == [{"page": 1, "id": 9, "x": 6, "text": "False"}]
        # a part that a .cmd file runs too is a page file: rendered on its own with its defaults
        assert self.render(components["common/parts/dot.jsonl"]) == [{"page": 1, "id": 1, "x": 2}]


class TestErrors(IncludeTestBase):
    @pytest.mark.parametrize(
        "directive, message",
        [
            ({"!import": "a.jsonl"}, "Unknown directive !import: the only directive is !include"),
            ({"!include": "a.jsonl", "page": 1}, "An !include has only 'vars' and 'for' next to its path, not page"),
            ({"!include": 5}, "The path of an !include must be a text"),
            ({"!include": " "}, "The path of an !include must be a text"),
            ({"!include": "{{ part }}.jsonl"}, "The path of an !include can't be a template"),
            ({"!include": "a.json"}, "An !include includes a .jsonl file, not: a.json"),
            ({"!include": "a.jsonl", "vars": [1]}, "'vars' of an !include must be an object of names and values"),
            ({"!include": "a.jsonl", "for": {"a b": [1]}}, "'a b' of 'for' is not a name that templates can use"),
            ({"!include": "a.jsonl", "for": {"i": "1, 2"}}, "'for' of 'i' must be a list or a single template"),
            ({"!include": "a.jsonl", "vars": {"i": 1}, "for": {"i": [1]}}, "i is in 'vars' and in 'for': use one of them"),
        ],
    )
    def test_directive_error(self, directive, message):
        assert directive_error(directive).startswith(message)

    def test_objects_are_no_directives(self):
        assert directive_error({"page": 1, "id": 2}) is None
        assert directive_error({"!include": "common/a.jsonl", "vars": {}, "for": {"i": "{{ range(3) }}"}}) is None
        assert not is_directive({"page": 1})
        assert directive_paths([{"page": 1}, {"!include": "a.jsonl"}, {"!include": 3}, {"!x": "b.jsonl"}]) == ["a.jsonl"]

    def test_an_error_of_a_directive_has_its_file_and_line(self, tmp_path):
        # GIVEN
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ id }}"}',
                "devices/plate/page.jsonl": '{"page": 1, "id": 1}\n{"!include": "common/parts/dot.jsonl", "vars": {"id": 2}, "x": 1}',
            },
        )

        # WHEN
        with pytest.raises(IncludeExpansionError) as error:
            self.processor.normalize(self.device, components["devices/plate/page.jsonl"])

        # THEN
        (found,) = error.value.errors
        assert (found.file, found.line, found.includes) == (tmp_path / "devices/plate/page.jsonl", 2, ())
        assert str(error.value).startswith("devices/plate/page.jsonl:2: An !include has only 'vars' and 'for'")

    def test_files_that_cant_be_included(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "devices/other/page.jsonl": '{"page": 1, "id": 1}',
                "devices/plate/page.jsonl": """
                    {"!include": "common/parts/missing.jsonl"}
                    {"!include": "devices/other/page.jsonl"}
                """,
            },
        )

        assert self.errors(components["devices/plate/page.jsonl"]) == [
            "The file to include doesn't exist: common/parts/missing.jsonl",
            "devices/other/page.jsonl is not a file of the device plate: only the files in common/ and in the folder of the "
            "device can be included",
        ]

    def test_a_cycle_names_the_chain(self, tmp_path):
        # GIVEN
        components = self.setup_config(
            tmp_path,
            {
                "common/a.jsonl": '{"page": 1, "id": 1}\n{"!include": "common/b.jsonl"}',
                "common/b.jsonl": '{"!include": "common/a.jsonl"}',
                "devices/plate/page.jsonl": '{"!include": "common/a.jsonl"}',
            },
        )

        # WHEN
        expansion = self.processor.expand_jsonl_objects(components["devices/plate/page.jsonl"])

        # THEN: the objects up to the cycle are there
        (error,) = expansion.errors
        assert error.message == (
            "The !includes include each other in a cycle: "
            "devices/plate/page.jsonl:1 -> common/a.jsonl:2 -> common/b.jsonl:1 -> common/a.jsonl"
        )
        assert (error.file, error.line) == (tmp_path / "common/b.jsonl", 1)
        assert [step.file for step in error.includes] == [tmp_path / "devices/plate/page.jsonl", tmp_path / "common/a.jsonl"]
        assert [obj.name for obj in expansion.objects] == ["p1b1"]

    def test_a_file_that_includes_itself(self, tmp_path):
        components = self.setup_config(tmp_path, {"devices/plate/page.jsonl": '{"!include": "devices/plate/page.jsonl"}'})

        assert self.errors(components["devices/plate/page.jsonl"]) == [
            "The !includes include each other in a cycle: devices/plate/page.jsonl:1 -> devices/plate/page.jsonl"
        ]

    @pytest.mark.parametrize(
        "directive, message",
        [
            ('"vars": {"id": "{{ nope }}"}', "Can't render 'id': 'nope' is undefined: {{ nope }}"),
            ('"vars": {"id": 1, "x": {"y": ["{{ nope }}"]}}', "Can't render 'x.y': 'nope' is undefined: {{ nope }}"),
            (
                '"vars": {"id": 1, "x": "{{ b4.x + 10 }}"}',
                "'x' refers to the object b4, but the variables of an !include are rendered before the objects. Pass its id",
            ),
            ('"vars": {"id": 1, "x": "{{ this.x }}"}', "'x' refers to the object this, but"),
            ('"vars": {"id": 1, "x": "{{ b{{ a }}.x }}"}', "Can't render 'x': 'a' is undefined"),
            ('"vars": {"id": 1, "x": "{{ 1 + }}"}', "Can't render 'x': unexpected 'end of template': {{ 1 + }}"),
            ('"for": {"id": "{{ 5 }}"}', "'for' of 'id' is not a list of values: 5"),
            ('"for": {"id": "{{ \'abc\' }}"}', "'for' of 'id' is not a list of values: 'abc'"),
            ('"for": {"id": "{{ nope }}"}', "Can't render 'for.id': 'nope' is undefined"),
            ('"for": {"id": "{{ range(2000) }}"}', f"'for' of 'id' has 2000 values, more than {MAX_INSTANCES}"),
            (
                '"for": {"id": "{{ range(50) }}", "b": "{{ range(50) }}"}',
                f"'for' makes 2500 instances, more than {MAX_INSTANCES}",
            ),
            ('"vars": {"id": 1, "box": 3}', "Incompatible types for merging dict"),
            ('"vars": {"id": "x"}', "The page and id of an included object must be numbers, not 1 and 'x'"),
            ('"vars": {}', "Can't render the page and id of the object: 'id' is undefined"),
        ],
    )
    def test_templates_that_cant_be_rendered(self, tmp_path, directive, message):
        components = self.setup_config(
            tmp_path,
            {
                "devices/plate/vars.yaml": "box:\n  x: 1\n",
                "common/dot.jsonl": '{"page": 1, "id": "{{ id }}"}',
                "devices/plate/page.jsonl": '{"page": 1, "id": 4}\n{"!include": "common/dot.jsonl", ' + directive + "}",
            },
        )

        (error,) = self.errors(components["devices/plate/page.jsonl"])
        assert error.startswith(message)

    def test_an_error_in_the_defaults_of_a_part(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ id }}"}',
                "common/parts/dot.vars.yaml": 'size: "{{ nope }}"\n',
                "devices/plate/page.jsonl": '{"!include": "common/parts/dot.jsonl", "vars": {"id": 1}}',
            },
        )

        assert self.errors(components["devices/plate/page.jsonl"]) == [
            "Unknown variable 'nope' in the variable 'size': {{ nope }}"
        ]

    def test_an_error_in_a_part_has_the_line_in_the_part_and_the_chain(self, tmp_path):
        # GIVEN
        components = self.setup_config(
            tmp_path,
            {
                "common/parts/dot.jsonl": '{"page": 1, "id": "{{ id }}"}\n{"page": 1, "id": 99, "text": "{{ caption + 1 }}"}',
                "devices/plate/page.jsonl": '{"!include": "common/parts/dot.jsonl", "vars": {"caption": "a"}, "for": {"id": [1]}}',
            },
        )

        # WHEN
        with pytest.raises(IncludedObjectError) as error:
            self.processor.normalize(self.device, components["devices/plate/page.jsonl"])

        # THEN
        assert (error.value.origin.file, error.value.origin.line) == (tmp_path / "common/parts/dot.jsonl", 2)
        assert str(error.value).startswith("common/parts/dot.jsonl:2: ")
        assert str(error.value).endswith("(included at devices/plate/page.jsonl:1 (id=1))")
        assert error.value.reason == 'can only concatenate str (not "int") to str'

    def test_ids_of_included_objects_that_other_objects_have(self, tmp_path):
        # GIVEN: an instance has the id of an object of the file, and two instances have the same ids
        components = self.setup_config(
            tmp_path,
            {
                "common/dot.jsonl": '{"page": 1, "id": "{{ id }}"}',
                "devices/plate/vars.yaml": "page: 1\n",
                "devices/plate/page.jsonl": """
                    {"page": "{{ page }}", "id": 3}
                    {"!include": "common/dot.jsonl", "for": {"id": [3, 4, 4]}}
                    {"page": 1, "id": "{{ p1b1.x }}"}
                """,
            },
        )

        # WHEN
        expansion = self.processor.expand_jsonl_objects(components["devices/plate/page.jsonl"])

        # THEN: reported at the directive, once for every object that has the name of an object before it
        assert [(error.line, error.message) for error in expansion.errors] == [
            (2, "p1b3 of common/dot.jsonl:1 (id=3) is also the id of devices/plate/page.jsonl"),
            (2, "p1b4 of common/dot.jsonl:1 (id=4) is also the id of common/dot.jsonl:1 (id=4)"),
        ]

    def test_an_included_object_that_comes_first_has_the_id_of_an_object_of_the_file(self, tmp_path):
        components = self.setup_config(
            tmp_path,
            {
                "common/dot.jsonl": '{"page": 1, "id": 3}',
                "devices/plate/page.jsonl": '{"!include": "common/dot.jsonl"}\n{"page": 1, "id": 3}',
            },
        )

        assert self.errors(components["devices/plate/page.jsonl"]) == [
            "p1b3 of common/dot.jsonl:1 is also the id of devices/plate/page.jsonl"
        ]


class TestDisplay:
    def test_paths_outside_of_the_config_directory_stay_as_they_are(self, tmp_path):
        assert display_path(Path("/elsewhere/a.jsonl"), tmp_path) == "/elsewhere/a.jsonl"
        assert display_path(tmp_path / "common" / "a.jsonl", tmp_path) == "common/a.jsonl"

    def test_steps_with_loops(self, tmp_path):
        steps = (IncludeStep(tmp_path / "a.jsonl", 0, 4, {}, {"row": 1, "name": "x"}),)
        assert describe_includes(steps, tmp_path) == "included at a.jsonl:4 (row=1, name='x')"
