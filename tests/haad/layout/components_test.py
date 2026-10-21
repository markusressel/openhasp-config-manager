from datetime import timedelta

import pytest

from haad.triggers import Trigger
from haad.ui import Card
from openhasp_config_manager.haad.layout.components import (
    Bar, Button, Column, Grid, Image, Label, Obj, Page, Panel, Row, SceneButton, Slider, Spacer, Stack, Switch,
)
from openhasp_config_manager.haad.layout.geometry import Padding, Rect
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


def test_column_and_row_layout():
    with Page(padding=Padding(bottom=48)) as page:
        with Column(gap=4, padding=8):
            header = Label(text="Header", size=40)
            with Row(gap=8, weight=1) as row:
                left = Label(text="L", weight=2)
                right = Switch(size="25%")
                spacer = Spacer()
            footer = Label(text="Footer", size="10%")

    page.layout(320, 480)

    # content: 8..312 x 8..424 (480 - 48 bottom padding - 8)
    assert header.rect == Rect(8, 8, 304, 40)
    # 416 - 40 - 41 (10%) - 2 gaps = 327
    assert row.rect == Rect(8, 52, 304, 327)
    assert footer.rect == Rect(8, 383, 304, 41)
    # 304 - 76 (25%) - 16 gaps = 212, shared 2:1
    assert left.rect == Rect(8, 52, 141, 327)
    assert right.rect == Rect(157, 52, 76, 327)
    assert spacer.rect == Rect(241, 52, 71, 327)


def test_grid_layout():
    with Page() as page:
        with Grid(columns=2, gap=10, padding=10):
            cells = [Label(text=str(i)) for i in range(3)]
        with Grid(columns=3):
            pass

    page.layout(320, 480)

    # 2 rows (3 children, 2 columns); the page gives each grid half of the screen
    assert [c.rect for c in cells] == [Rect(10, 10, 145, 105), Rect(165, 10, 145, 105), Rect(10, 125, 145, 105)]


def test_grid_rejects_sizes():
    with Page() as page:
        with Grid(columns=2):
            Label(size=10)

    with pytest.raises(ValueError, match="grid cells are equal"):
        page.layout(100, 100)


def test_grid_needs_columns():
    with Page():
        with pytest.raises(ValueError, match="at least one column"):
            Grid(columns=0)


def test_stack_and_at():
    with Page() as page:
        with Stack(padding=5, size=40):
            bar = Bar()
            label = Label(text="50%")
        pinned = Label(text="x", at=Rect("50%", 10, 20, "10%"))

    page.layout(200, 100)

    assert bar.rect == label.rect == Rect(5, 5, 190, 30)
    # at= is relative to the parent's content area and takes no space in the flow
    assert pinned.rect == Rect(100, 10, 20, 10)


def test_panel_children_are_relative_to_the_panel():
    with Page() as page:
        with Panel(direction="row", size=40, padding=Padding(x=6), bg_color="#558B2F") as panel:
            clock = Label(text="12:00")
            title = Label(text="Title", weight=2)
        Spacer()

    page.layout(320, 480)

    assert panel.rect == Rect(0, 0, 320, 40)
    assert clock.rect == Rect(6, 0, 102, 40)
    assert title.rect == Rect(108, 0, 206, 40)
    assert panel.props == {"bg_color": "#558B2F"}


def test_panel_direction_must_be_valid():
    with Page():
        with pytest.raises(ValueError, match="Invalid direction"):
            Panel(direction="diagonal")


def test_nodes_outside_a_page_raise():
    with pytest.raises(ValueError, match="Label created outside of a `with Page\\(\\)` block"):
        Label(text="x")
    with pytest.raises(ValueError, match="Row created outside"):
        Row()


def test_nested_pages_raise():
    with Page():
        with pytest.raises(ValueError, match="can't be nested"):
            Page()


def test_size_and_weight_exclude_each_other():
    with Page():
        with pytest.raises(ValueError, match="exclude each other"):
            Label(size=10, weight=2)


def test_external_page_rejects_layout():
    with Page(external=True):
        Switch(obj_id=22)
        for factory in [Row, Column, Stack, Spacer, lambda: Grid(columns=2), Panel]:
            with pytest.raises(ValueError, match="in Page\\(external=True\\): the layout is on the plate's flash"):
                factory()
        for sizing in [dict(size=10), dict(weight=1), dict(at=Rect(0, 0, 1, 1))]:
            with pytest.raises(ValueError, match="size=, weight= and at= in Page\\(external=True\\)"):
                Label(obj_id=1, **sizing)


def test_families_do_not_mix():
    with Page() as page:
        with Card() as card:
            label = Label(text="x")

    assert page.children == [label]
    assert card.children == []


def test_obj_before_mount_raises():
    with Page():
        label = Label(text="x")

    with pytest.raises(RuntimeError, match="Label \\(components_test.py:\\d+\\) is not mounted yet"):
        label.obj


def test_leaves_and_nodes():
    with Page() as page:
        a = Label()
        with Row() as row:
            b = Switch()
            spacer = Spacer()

    assert page.leaves() == [a, b]
    assert page.nodes() == [a, row, b, spacer]


async def test_mount_owned_page(page: PageController, plate: FakePlate):
    async def on_click():
        pass

    with Page() as layout:
        with Panel(direction="row", size=40, bg_color="#000") as panel:
            title = Label(text="Title", text_font=32)
        with Column(weight=1):
            switch = Switch(entity="light.desk", obj_id=3)
            scene = SceneButton(scene="work", text="Work")
            button = Button(text="Pause", on_click=on_click)
            slider = Slider(entity="sensor.volume")
            bar = Bar(entity="sensor.p", trigger=Trigger.Time.every(interval=timedelta(seconds=1)))
            image = Image()
            arc = Obj(type="arc", min=0)
            border = Label(text="x", border_width=Bound("sensor.co2", lambda x: 1))

    layout.layout(320, 480)
    await layout.mount(page)

    # explicit ids are reserved, the others are allocated in declaration order (the panel first)
    assert [n.obj.obj_id for n in [panel, title, switch, scene, button, slider, bar, image, arc, border]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert title.obj.parent is panel.obj
    assert switch.obj.parent is None
    assert title.obj.rect == Rect(0, 0, 320, 40)
    assert switch.obj.rect == Rect(0, 40, 320, 55)
    assert title.obj.props == {"text": "Title", "text_font": 32}
    assert panel.obj.props == {"bg_color": "#000"}
    assert arc.obj.obj_type == "arc" and arc.obj.props == {"min": 0}
    assert scene.obj.scene == "work"
    assert bar.obj.trigger is not None
    assert switch.obj._entity_id == "light.desk"
    assert list(border.obj.bound_props) == ["border_width"]
    assert title.obj.declaration.startswith("components_test.py:") and title.obj.declaration.endswith(" Label")
    assert page.owned
    assert plate.commands == []


async def test_mount_external_page(page: PageController):
    with Page(external=True) as layout:
        label = Label(obj_id=12, entity="sensor.co2", text=lambda x: f"{x}ppm", mode="scroll")
        switch = Switch(obj_id=22, entity="light.desk")

    await layout.mount(page)

    assert label.obj.obj_id == 12 and not label.obj.owned
    assert label.obj.props == {"mode": "scroll"}
    assert switch.obj is page.objects[22]
    assert not page.owned


async def test_mount_external_page_needs_ids(page: PageController):
    with Page(external=True) as layout:
        Switch(obj_id=22)
        Label()

    with pytest.raises(ValueError, match="Page\\(external=True\\) needs an obj_id on every leaf, missing on: Label \\(components_test"):
        await layout.mount(page)


async def test_mount_pinned_page_needs_ids(page: PageController):
    with Page(pin_ids=True) as layout:
        Label()

    layout.layout(100, 100)
    with pytest.raises(ValueError, match="Page\\(pin_ids=True\\) needs an obj_id"):
        await layout.mount(page)


async def test_mount_owned_page_needs_a_layout(page: PageController):
    with Page() as layout:
        Label()

    with pytest.raises(ValueError, match="needs a layout\\(\\) first"):
        await layout.mount(page)


async def test_abstract_nodes():
    from openhasp_config_manager.haad.layout.components import Container, Leaf

    with Page():
        container = Container()
        leaf = Leaf()

    with pytest.raises(NotImplementedError):
        container._arrange(Rect(0, 0, 1, 1), [])
    with pytest.raises(NotImplementedError):
        await leaf._add(None, {})
