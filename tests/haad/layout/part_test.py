"""`Part`: the parts of the config directory in code-defined layouts (README §4.4.2, docs/config-model-api.md)."""

import shutil
import textwrap
from pathlib import Path
from typing import Dict

import pytest

from openhasp_config_manager.haad.layout.components import Column, Label, Page, Panel, Part, Repeat, Row
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.objects.button import ButtonObjectController
from openhasp_config_manager.haad.objects.generic import GenericObjectController
from openhasp_config_manager.haad.objects.label import LabelObjectController
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import PlateConfig, Screen
from openhasp_config_manager.processing.jsonl.includes import IncludeExpansionError
from tests.haad.conftest import CFG_ROOT, PlateUnderTest, page_at
from tests.haad.fakes import FakePlate, Mqtt

# the theme of the plate: the objects of the parts don't get it, they get the one of the config
THEME = Theme(background_color="#101010", obj={"label": {"text_color": "#FFFFFF"}, "btn": {"radius": 3}})

PARTS = {
    "theme.yaml": """
        theme:
          obj:
            label:
              text_color: "#DEE8DF"
            btn:
              radius: 14
        """,
    "common/common.vars.yaml": """
        common:
          header:
            height: 27
        """,
    # the bar behind the header
    "common/parts/header/bar.jsonl": """
        {"page": "{{ page_index }}", "id": 1, "obj": "btn", "x": 0, "y": 0, "w": "100%", "h": "{{ common.header.height }}", "text": ""}
        """,
    # the time and the title, on the bar of the other part (b1)
    "common/parts/header/header.jsonl": """
        {"page": "{{ page_index }}", "id": 10, "obj": "label", "x": 8, "y": 2, "w": "20%", "h": "{{ b1.h - 4 }}", "text": "00:00"}
        {"page": "{{ page_index }}", "id": 11, "obj": "label", "x": "{{ this.w // 2 }}", "y": 2, "w": "50%", "h": "{{ b1.h - 4 }}", "text": "{{ header.title }}", "align": "center"}
        """,
    # a part for code layouts: it fills the area it gets, and a label next to an object of the page
    "common/parts/box.jsonl": """
        {"page": "{{ page_index }}", "id": "{{ box.id }}", "obj": "obj", "x": "{{ area.x }}", "y": "{{ area.y }}", "w": "{{ area.w }}", "h": "{{ area.h }}"}
        {"page": "{{ page_index }}", "id": "{{ box.id + 1 }}", "obj": "label", "x": "{{ b{{ box.anchor }}.x + b{{ box.anchor }}.w }}", "y": "{{ area.y }}", "w": 10, "h": 10, "text": "x"}
        """,
}


def write_config(config_dir: Path, files: Dict[str, str]) -> Path:
    """The test config directory (`tests/_test_cfg_root`, device `test_device`, 480x320) with the files."""
    shutil.copytree(CFG_ROOT, config_dir)
    for name, content in files.items():
        path = config_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + "\n")
    return config_dir


@pytest.fixture
def config_dir(tmp_path) -> Path:
    return write_config(tmp_path / "config", PARTS)


class PartsPlate(PlateUnderTest):
    @property
    def plate_config(self) -> PlateConfig:
        return PlateConfig(theme=THEME)


class HeaderPage(PageController):
    """The frame of haad-home's code pages: a header from parts, the clock bound in code."""

    async def build_layout(self) -> Page:
        with Page() as page:
            Part("common/parts/header/bar.jsonl", at=Rect(0, 0, 0, 0))
            self.header = Part("common/parts/header/header.jsonl", vars={"header": {"title": "Alerts"}}, size=27)
            with Column(padding=4, gap=4):
                self.first = Label(text="First", size=40)
                self.box = Part("common/parts/box.jsonl", vars={"box": {"id": 30, "anchor": 2}}, size=20)
                Label(text="Last", size=20)
        return page

    async def register_objects(self):
        await self.header.obj(10, LabelObjectController).bind_text(entity="sensor.time")


async def start(start_plate, config_dir: Path, page_class=HeaderPage) -> PageController:
    controller = await start_plate(PartsPlate, pages=[page_at(1, page_class)], config_dir=config_dir)
    return controller.plate_controller.pages[1]


def _jsonl(page: PageController, obj_id: int) -> Dict:
    return next(o for o in page.plate.rendered[page.index] if o["id"] == obj_id)


async def test_the_objects_of_parts_are_rendered_by_the_config(simulator, start_plate, plate: FakePlate, config_dir):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")

    page = await start(start_plate, config_dir)

    rendered = page.plate.rendered[1]
    # in the order of the tree; the ids of the parts are skipped by the other objects (1 is the bar)
    assert [o["id"] for o in rendered] == [0, 1, 10, 11, 2, 30, 31, 3]
    # the theme of the config, not the one of the plate, and percentages of the device's screen (480x320)
    assert _jsonl(page, 1) == {
        "page": 1,
        "id": 1,
        "obj": "btn",
        "x": 0,
        "y": 0,
        "w": 480,
        "h": 27,
        "text": "",
        "radius": 14,
    }
    # referring to an object of another part, and to itself
    assert _jsonl(page, 11) == {
        "page": 1,
        "id": 11,
        "obj": "label",
        "x": 120,
        "y": 2,
        "w": 240,
        "h": 23,
        "text": "Alerts",
        "align": "center",
        "text_color": "#DEE8DF",
    }
    # the other objects get the theme of the plate
    assert _jsonl(page, 2)["text_color"] == "#FFFFFF"
    # placed in its area (relative to the screen), next to an object of the page (b2)
    assert page.box.rect == Rect(4, 75, 472, 20)
    assert _jsonl(page, 30) == {"page": 1, "id": 30, "obj": "obj", "x": 4, "y": 75, "w": 472, "h": 20}
    assert (_jsonl(page, 31)["x"], _jsonl(page, 31)["y"]) == (476, 75)
    # pushed with the page, then the clock follows its entity
    assert Mqtt("hasp/mqtt_name/command/clearpage", 1) in plate.traffic
    assert Mqtt("hasp/mqtt_name/command", "p1b10.text=12:00") in plate.traffic

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.time", "12:01")
    await plate.settle()
    assert plate.commands == ["p1b10.text=12:01"]


async def test_like_the_config_renders_them(start_plate, config_dir):
    page = await start(start_plate, config_dir)
    model = page.plate.config_model

    # exactly what the config renders for an instance of the part, with the other objects of the page
    objects = {o["id"]: o for o in page.plate.rendered[1] if o["id"] not in (0, 30, 31)}
    expected = model.render_part(
        "common/parts/box.jsonl",
        page=1,
        vars={"box": {"id": 30, "anchor": 2}, "area": {"x": 4, "y": 75, "w": 472, "h": 20}},
        objects=objects,
    )
    assert [_jsonl(page, 30), _jsonl(page, 31)] == [dict(o.jsonl) for o in expected]


async def test_the_object_controllers_of_a_part(start_plate, config_dir):
    page = await start(start_plate, config_dir)

    bar = page.layout_root.children[0]
    assert isinstance(bar.obj(1), ButtonObjectController)
    assert bar.obj(1) is page.objects[1]
    assert isinstance(page.box.obj(30), GenericObjectController) and page.box.obj(30).obj_type == "obj"
    assert page.header.obj(11, ObjectController) is page.header.obj(11, LabelObjectController)
    assert page.header.ids == [10, 11]
    assert all(page.objects[i].owned and page.objects[i].part is page.header for i in [10, 11])
    # where they are written, for the layout dumps
    assert page.objects[11].declaration.endswith("Part common/parts/header/header.jsonl:2")
    with pytest.raises(ValueError, match=r"Part\(common/parts/header/header.jsonl\) has no object 12, only: 10, 11"):
        page.header.obj(12)
    with pytest.raises(
        TypeError, match="Object p1b10 of Part\\(common/parts/header/header.jsonl\\) is a LabelObjectController, not a"
    ):
        page.header.obj(10, ButtonObjectController)


async def test_property_changes_before_the_push_are_part_of_the_pushed_objects(start_plate, config_dir):
    class ChangingPage(HeaderPage):
        async def register_objects(self):
            await self.header.obj(11, LabelObjectController).set_text("Changed")

    page = await start(start_plate, config_dir, ChangingPage)

    assert _jsonl(page, 11)["text"] == "Changed"


async def test_obj_and_ids_before_the_mount():
    with Page():
        part = Part("common/parts/header/bar.jsonl")
    with pytest.raises(RuntimeError, match="is not mounted yet"):
        part.obj(1)
    with pytest.raises(RuntimeError, match="is not expanded yet"):
        part.ids


async def test_where_a_part_can_be():
    with Page(external=True):
        with pytest.raises(ValueError, match="in Page\\(external=True\\): the objects of a part are pushed by haad"):
            Part("common/parts/header/bar.jsonl")
    with Page():
        with Panel():
            with Row():
                with pytest.raises(ValueError, match="in a Panel"):
                    Part("common/parts/header/bar.jsonl")
        with pytest.raises(ValueError, match="'area' of a part is its rectangle in the layout"):
            Part("common/parts/box.jsonl", vars={"area": {}})


async def test_not_in_a_repeat(start_plate, config_dir):
    class ListPage(PageController):
        async def build_layout(self) -> Page:
            async def values():
                return [1]

            async def item(value):
                Part("common/parts/header/bar.jsonl")

            with Page() as page:
                Repeat(values, item, trigger="sensor.time")
            return page

    page = PageController.__new__(ListPage)
    layout = await page.build_layout()
    with pytest.raises(ValueError, match="in a Repeat: the items of a list can't have parts"):
        await layout.expand()


async def _mount(page: PageController, layout: Page):
    layout.layout(page.plate.screen.width, page.plate.screen.height)
    await layout.mount(page)


async def test_an_explicit_id_of_a_part_raises(start_plate, config_dir):
    page = await start(start_plate, config_dir)
    page.objects.clear()
    with Page() as layout:
        Part("common/parts/header/bar.jsonl")
        Label(obj_id=1)

    with pytest.raises(ValueError, match="Object with id 1 already exists on page 1"):
        await _mount(page, layout)


async def test_errors_of_the_config(start_plate, config_dir):
    files = {
        "common/parts/other_page.jsonl": '{"page": 0, "id": 1, "obj": "label"}',
        "common/parts/no_type.jsonl": '{"page": "{{ page_index }}", "id": 1}',
        "common/parts/twice.jsonl": '{"page": "{{ page_index }}", "id": 1, "obj": "label"}\n{"page": "{{ page_index }}", "id": 1, "obj": "label"}',
    }
    for name, content in files.items():
        (config_dir / name).write_text(content)
    page = await start(start_plate, config_dir)
    # the config is read when the plate starts
    page.plate.config_model = type(page.plate.config_model).load(config_dir, "test_device")

    for path, error, match in [
        (
            "common/parts/other_page.jsonl",
            ValueError,
            "common/parts/other_page.jsonl:1: the object is on page 0, not on page 1",
        ),
        (
            "common/parts/no_type.jsonl",
            ValueError,
            "common/parts/no_type.jsonl:1: an object of a part on a page pushed by haad needs an obj",
        ),
        ("common/parts/twice.jsonl", IncludeExpansionError, "p1b1 of common/parts/twice.jsonl:2 is also the id of"),
        ("common/parts/nope.jsonl", IncludeExpansionError, "The file to include doesn't exist"),
    ]:
        page.objects.clear()
        with Page() as layout:
            Part(path)
        with pytest.raises(error, match=match):
            await _mount(page, layout)


async def test_a_plate_without_config_model(start_plate, config_dir):
    page = await start(start_plate, config_dir)
    page.objects.clear()
    page.plate.config_model = None
    with Page() as layout:
        Part("common/parts/header/bar.jsonl")

    with pytest.raises(ValueError, match="parts need a plate with a config_dir"):
        await _mount(page, layout)


async def test_the_screen_of_the_plate_must_be_the_one_of_the_config(start_plate, config_dir):
    class SmallPlate(PartsPlate):
        @property
        def plate_config(self) -> PlateConfig:
            return PlateConfig(theme=THEME, screen=Screen(320, 240))

    controller = await start_plate(SmallPlate, pages=[page_at(1)], config_dir=config_dir)
    page = controller.plate_controller.pages[1]
    page.objects.clear()
    with Page() as layout:
        Part("common/parts/header/bar.jsonl")

    with pytest.raises(
        ValueError,
        match=r"the plate's screen Screen\(width=320, height=240\) is not the one of its device in the config \(480x320\)",
    ):
        await _mount(page, layout)


async def test_a_part_can_not_move(simulator, start_plate, config_dir):
    class CollapsingPage(PageController):
        async def build_layout(self) -> Page:
            with Page() as page:
                Label(text="Hidden", size=20, hidden=Bound("binary_sensor.x", lambda x: "1" if x == "on" else "0"))
                Part("common/parts/box.jsonl", vars={"box": {"id": 30, "anchor": 1}}, size=20)
            return page

    await simulator.ha.trigger_state_change("binary_sensor.x", "off")
    page = await start(start_plate, config_dir, CollapsingPage)

    with pytest.raises(
        ValueError, match=r"Part\(common/parts/box.jsonl\) .* moved from Rect\(x=0, y=20, w=480, h=20\) to Rect\(x=0, y=0"
    ):
        await page.layout_root.children[0].set_collapsed(True)
