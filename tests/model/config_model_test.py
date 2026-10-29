import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, List

import pytest

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.model import ConfigModel, PartObject
from openhasp_config_manager.processing.jsonl.includes import IncludedObjectError, IncludeExpansionError
from openhasp_config_manager.processing.template_rendering import TemplateRenderError
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase

TILE = """
    // a caption and its value below it, next to the card (b4). Parameters: page_index, tile.id, tile.caption
    {"page": "{{ page_index }}", "id": "{{ tile.id }}", "obj": "label", "x": "{{ b4.x + common.margin }}", "y": "{{ b4.y }}", "w": "50%", "h": "{{ tile.caption_h }}", "text": "{{ tile.caption }}"}
    {"page": "{{ page_index }}", "id": "{{ tile.id + 1 }}", "obj": "label", "x": "{{ b{{ tile.id }}.x }}", "y": "{{ b{{ tile.id }}.y + tile.value_dy }}", "w": "{{ this.h * 2 }}", "h": 30, "text": "{{ device.screen.width }}", "text_color": "#FF0000"}
    """

FILES = {
    "global.vars.yaml": "id:\n  time: 10\n",
    "theme.yaml": "theme:\n  obj:\n    label:\n      text_color: '#DEE8DF'\n      border_width: 0\n",
    "common/common.vars.yaml": "common:\n  margin: 4\n  double_margin: '{{ common.margin * 2 }}'\n",
    "common/parts/tile/tile.jsonl": TILE,
    # the defaults of the part, computed from its parameters and the variables of the device
    "common/parts/tile/tile.yaml": "tile:\n  caption_h: 20\n  value_dy: '{{ tile.caption_h + common.margin }}'\n",
    # a file that includes the part, as the reference for the model
    "common/code.jsonl": """
        {"page": 4, "id": 4, "obj": "obj", "x": 10, "y": 40, "w": 200, "h": 100}
        {"!include": "common/parts/tile/tile.jsonl", "vars": {"tile": {"id": 20, "caption": "Elapsed"}, "page_index": 4}}
        """,
    "devices/plate/boot.cmd": "run L:/common_code.jsonl\n",
    # the device overrides a variable that others are computed from
    "devices/plate/device.vars.yaml": "common:\n  margin: 6\n",
    "devices/other/boot.cmd": "\n",
}

# the objects of the page in common/code.jsonl, as they are sent to the plate
PAGE_OBJECTS = {4: {"page": 4, "id": 4, "obj": "obj", "x": 10, "y": 40, "w": 200, "h": 100}}
TILE_VARS = {"tile": {"id": 20, "caption": "Elapsed"}}


def write_config(config_dir: Path, files: Dict[str, str]) -> Path:
    """A config directory with the files and the devices `plate` and `other` (480x320: rotated)."""
    device_config = json.loads((TestBase.cfg_root / "devices" / "test_device" / "config.json").read_text())
    for name in ["plate", "other"]:
        folder = config_dir / "devices" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "config.json").write_text(json.dumps(device_config))
    for name, content in files.items():
        path = config_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + "\n")
    return config_dir


def generate(config_dir: Path, output_dir: Path, device: str, file: str) -> List[Dict]:
    """:return: the objects of a file as `generate` writes them"""
    manager = ConfigManager(config_dir, output_dir, VariableManager(config_dir))
    manager.process(next(d for d in manager.analyze() if d.name == device))
    return [json.loads(line) for line in (output_dir / device / file).read_text().splitlines()]


@pytest.fixture
def config_dir(tmp_path) -> Path:
    return write_config(tmp_path / "config", FILES)


@pytest.fixture
def model(config_dir) -> ConfigModel:
    return ConfigModel.load(config_dir, "plate")


class TestLoad:
    def test_the_device(self, model, config_dir):
        assert model.config_dir == config_dir
        assert model.device.name == "plate"
        assert model.device.path == config_dir / "devices" / "plate"
        assert model.device.ip == "1.2.3.4"
        # rotated
        assert (model.device.screen.width, model.device.screen.height) == (480, 320)
        assert model.device.gui.idle1 == 60
        assert model.device.hasp.pages == "/pages.jsonl"

    def test_the_device_has_no_credentials(self, model):
        assert not any("password" in field or field in ("wifi", "mqtt", "http") for field in vars(model.device))

    def test_unknown_device(self, config_dir):
        with pytest.raises(ValueError, match="Unknown device: nope, the devices of .* are: other, plate"):
            ConfigModel.load(config_dir, "nope")

    def test_no_qt(self):
        # the model is for code outside of the GUI: it must not need Qt
        code = "import sys, openhasp_config_manager.model as m; print([n for n in sys.modules if n.startswith(('PyQt', m.__name__.replace('model', 'gui')))])"
        assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "[]"


class TestVariables:
    def test_the_variables_of_common_for_the_device(self, model):
        variables = model.variables()

        # the override of the device, and what is computed from it
        assert variables["common"]["margin"] == 6
        assert variables["common"]["double_margin"] == 12
        assert variables["id"] == {"time": 10}
        assert variables["theme"]["obj"]["label"]["text_color"] == "#DEE8DF"
        assert variables["device"].screen.width == 480

    def test_like_the_vars_command(self, model, config_dir):
        manager = ConfigManager(config_dir, Path("./nonexistent"), VariableManager(config_dir))
        manager.analyze()

        for path in ["common", "common/parts/tile/tile.jsonl", "devices/plate"]:
            expected = manager.variables_of_path(config_dir / path, "plate")
            assert model.variables(path) == {**expected, "device": model.variables()["device"]}

    def test_the_variables_of_a_part(self, model):
        # the defaults of the part next to those of common/, computed for the device
        assert model.variables("common/parts/tile")["tile"] == {"caption_h": 20, "value_dy": 26}
        assert model.variables("common/parts/tile")["common"] == model.variables()["common"]

    def test_a_variable_that_can_not_be_computed(self, tmp_path):
        model = ConfigModel.load(write_config(tmp_path / "config", {**FILES, "common/x.yaml": "x: '{{ nope }}'"}), "plate")
        with pytest.raises(TemplateRenderError, match="nope"):
            model.variables()

    def test_per_device(self, config_dir):
        assert ConfigModel.load(config_dir, "other").variables()["common"]["double_margin"] == 8

    def test_the_folder_of_another_device(self, model):
        with pytest.raises(ValueError, match="in the folder of the device 'other'"):
            model.variables("devices/other")


class TestRenderPart:
    def test_like_generate(self, model, config_dir, tmp_path):
        # THEN: the objects of the instance are those that `generate` writes for an `!include` of it with the same vars
        expected = generate(config_dir, tmp_path / "output", "plate", "common_code.jsonl")[1:]

        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=PAGE_OBJECTS)

        assert [dict(obj.jsonl) for obj in rendered] == expected
        # and what that is: references to the page (b4), to the part itself (b20, this), defaults computed with the variables
        # of the device, percentages in pixels, the theme of the config, numbers
        assert expected == [
            {
                "page": 4,
                "id": 20,
                "obj": "label",
                "x": 16,
                "y": 40,
                "w": 240,
                "h": 20,
                "text": "Elapsed",
                "text_color": "#DEE8DF",
                "border_width": 0,
            },
            {
                "page": 4,
                "id": 21,
                "obj": "label",
                "x": 16,
                "y": 66,
                "w": 60,
                "h": 30,
                "text": "480",
                "text_color": "#FF0000",
                "border_width": 0,
            },
        ]

    def test_the_origin(self, model, config_dir):
        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=PAGE_OBJECTS)

        part = config_dir / "common" / "parts" / "tile" / "tile.jsonl"
        assert [(obj.origin.file, obj.origin.line) for obj in rendered] == [(part, 2), (part, 3)]
        assert [model.describe(obj.origin) for obj in rendered] == [
            "common/parts/tile/tile.jsonl:2",
            "common/parts/tile/tile.jsonl:3",
        ]
        assert rendered[0].origin.includes[0].vars == {**TILE_VARS, "page_index": 4}

    def test_nested_parts(self, tmp_path):
        files = {
            **FILES,
            "common/parts/pair.jsonl": """
                {"!include": "common/parts/tile/tile.jsonl", "vars": {"tile": {"id": "{{ first }}", "caption": "A"}}}
                // the second one below the first
                {"!include": "common/parts/tile/tile.jsonl", "vars": {"tile": {"id": "{{ first + 2 }}", "caption": "B"}}}
                """,
            "common/code.jsonl": """
                {"page": 4, "id": 4, "obj": "obj", "x": 10, "y": 40, "w": 200, "h": 100}
                {"!include": "common/parts/pair.jsonl", "vars": {"first": 30, "page_index": 4}}
                """,
        }
        config_dir = write_config(tmp_path / "config", files)
        model = ConfigModel.load(config_dir, "plate")

        rendered = model.render_part("common/parts/pair.jsonl", page=4, vars={"first": 30}, objects=PAGE_OBJECTS)

        assert [dict(obj.jsonl) for obj in rendered] == generate(
            config_dir, tmp_path / "output", "plate", "common_code.jsonl"
        )[1:]
        assert [obj.jsonl["id"] for obj in rendered] == [30, 31, 32, 33]
        assert model.describe(rendered[2].origin) == "common/parts/pair.jsonl:3 > common/parts/tile/tile.jsonl:2"

    def test_the_objects_of_the_page_replace_those_of_the_files_on_it(self, model):
        # GIVEN: common/code.jsonl has an object 4 on page 4 too, at x=10: the page given here replaces it
        objects = {4: {**PAGE_OBJECTS[4], "x": 100}}

        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=objects)

        assert rendered[0].jsonl["x"] == 106

    def test_the_objects_of_the_files_on_other_pages(self, model):
        # GIVEN: the page given here is page 5, common/code.jsonl has nothing on it: b4 is the one of the page given here
        objects = {4: {"obj": "obj", "x": 50, "y": 0, "w": 10, "h": 10}}
        rendered = model.render_part("common/parts/tile/tile.jsonl", page=5, vars=TILE_VARS, objects=objects)
        assert [(obj.jsonl["page"], obj.jsonl["x"]) for obj in rendered] == [(5, 56), (5, 56)]

        # WHEN: nothing on page 5 is given
        with pytest.raises(IncludedObjectError, match="common/parts/tile/tile.jsonl:2: .*b4"):
            model.render_part("common/parts/tile/tile.jsonl", page=5, vars=TILE_VARS)

    def test_a_part_only_code_uses(self, tmp_path, capsys):
        # GIVEN: no file includes the part, so it is no part of a file of the device
        files = {**FILES, "common/code.jsonl": '{"page": 4, "id": 4, "obj": "obj", "x": 10, "y": 40, "w": 200, "h": 100}'}
        model = ConfigModel.load(write_config(tmp_path / "config", files), "plate")

        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=PAGE_OBJECTS)

        assert [obj.jsonl["id"] for obj in rendered] == [20, 21]
        # it is a part through the instance: its file is not rendered on its own, which would fail without the parameters
        assert "Can't render" not in capsys.readouterr().out

    def test_without_page_index_in_vars(self, model):
        with pytest.raises(ValueError, match="'page_index' of a part is its page, given by page="):
            model.render_part("common/parts/tile/tile.jsonl", page=4, vars={**TILE_VARS, "page_index": 4})

    def test_objects_of_another_page(self, model):
        with pytest.raises(ValueError, match="The object p4b4 of the page is p3b4"):
            model.render_part(
                "common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects={4: {**PAGE_OBJECTS[4], "page": 3}}
            )

    def test_a_part_that_does_not_exist(self, model):
        with pytest.raises(IncludeExpansionError, match="The file to include doesn't exist: common/parts/nope.jsonl"):
            model.render_part("common/parts/nope.jsonl", page=4)

    def test_a_part_of_another_device(self, tmp_path):
        files = {**FILES, "devices/other/part.jsonl": '{"page": "{{ page_index }}", "id": 1, "obj": "label"}'}
        model = ConfigModel.load(write_config(tmp_path / "config", files), "plate")
        with pytest.raises(IncludeExpansionError, match="is not a file of the device plate"):
            model.render_part("devices/other/part.jsonl", page=4)

    def test_an_unknown_variable(self, tmp_path):
        # GIVEN: `tile.caption` is missing
        code = FILES["common/code.jsonl"].replace(', "caption": "Elapsed"', "")
        config_dir = write_config(tmp_path / "config", {**FILES, "common/code.jsonl": code})
        model = ConfigModel.load(config_dir, "plate")

        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars={"tile": {"id": 20}}, objects=PAGE_OBJECTS)

        # THEN: like on a deployment, the template is not rendered (with a warning), and nothing fails
        expected = generate(config_dir, tmp_path / "output", "plate", "common_code.jsonl")[1:]
        assert [dict(obj.jsonl) for obj in rendered] == expected
        assert "{{" in rendered[0].jsonl["text"]

    def test_an_object_that_can_not_be_rendered(self, model):
        # `b4` is missing, and `b4.x + common.margin` can't be computed without it
        with pytest.raises(
            IncludedObjectError, match=r"common/parts/tile/tile.jsonl:2: .*b4.* \(included at common/<code page 4>.jsonl:1\)"
        ):
            model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS)

    def test_an_id_of_the_page(self, model):
        objects = {**PAGE_OBJECTS, 21: {"obj": "label", "x": 0, "y": 0, "w": 10, "h": 10}}
        with pytest.raises(IncludeExpansionError, match="p4b21 of common/parts/tile/tile.jsonl:3 is also the id of"):
            model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=objects)

    def test_invalid_objects(self, model):
        with pytest.raises(AssertionError, match="Object has invalid id '300'"):
            model.render_part(
                "common/parts/tile/tile.jsonl", page=4, vars={"tile": {"id": 300, "caption": "A"}}, objects=PAGE_OBJECTS
            )


class TestExpandPart:
    def test_the_objects_before_they_are_rendered(self, model, config_dir):
        # no objects of the page are needed: ids are rendered when the `!include` is expanded
        objects = model.expand_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS)

        part = config_dir / "common" / "parts" / "tile" / "tile.jsonl"
        assert [(o.page, o.id, o.obj, o.origin.file, o.origin.line) for o in objects] == [
            (4, 20, "label", part, 2),
            (4, 21, "label", part, 3),
        ]
        assert all(isinstance(o, PartObject) for o in objects)
        rendered = model.render_part("common/parts/tile/tile.jsonl", page=4, vars=TILE_VARS, objects=PAGE_OBJECTS)
        assert [(o.origin.file, o.origin.index) for o in objects] == [(o.origin.file, o.origin.index) for o in rendered]

    def test_the_type_from_a_template(self, tmp_path):
        files = {
            **FILES,
            "common/parts/any.jsonl": '{"page": "{{ page_index }}", "id": 1, "obj": "{{ kind }}"}\n{"page": "{{ page_index }}", "id": 2}',
        }
        model = ConfigModel.load(write_config(tmp_path / "config", files), "plate")

        assert [o.obj for o in model.expand_part("common/parts/any.jsonl", page=1, vars={"kind": "arc"})] == ["arc", None]
        with pytest.raises(IncludedObjectError, match="common/parts/any.jsonl:1: .*kind"):
            model.expand_part("common/parts/any.jsonl", page=1)

    def test_errors_of_the_expansion(self, model):
        with pytest.raises(IncludeExpansionError, match="Can't render the page and id of the object"):
            model.expand_part("common/parts/tile/tile.jsonl", page=4)
        with pytest.raises(ValueError, match="'page_index' of a part is its page"):
            model.expand_part("common/parts/tile/tile.jsonl", page=4, vars={"page_index": 1})
