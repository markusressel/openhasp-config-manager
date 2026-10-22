"""Plates with code-defined (owned) pages: render, push, re-push on LWT online, navigation (README §5)."""

import json
from datetime import timedelta

import pytest

from openhasp_config_manager.haad.layout.components import Button, Column, Label, Page, Panel, Repeat, Row, Switch
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import GuiDefaults, PlateConfig, Screen
from tests.haad.conftest import PlateUnderTest, page_at
from tests.haad.fakes import FakePlate, Http, Mqtt

THEME = Theme(background_color="#101010", obj={"label": {"text_color": "#FFFFFF"}})


class TreePage(PageController):
    async def build_layout(self) -> Page:
        with Page() as page:
            with Column(gap=10, padding=10):
                Label(text="Desk", text_font=32, size=40)
                with Row(gap=10):
                    self.clock = Label(entity="sensor.time")
                    Switch(entity="light.desk")
        return page

    async def register_objects(self):
        await self.clock.obj.set_border_width(1)


class ExplicitPage(PageController):
    async def register_objects(self):
        self.reboots = []
        await self.add_button(rect=Rect(0, 0, "50%", "50%"), text="Reboot", on_click=self._reboot)

    async def _reboot(self):
        self.reboots.append(True)


class ExternalTreePage(PageController):
    async def build_layout(self) -> Page:
        with Page(external=True) as page:
            Label(obj_id=10, entity="sensor.time", mode="scroll")
        return page


class MixedPage(PageController):
    async def register_objects(self):
        await self.add_label(obj_id=10)
        await self.add_label(rect=Rect(0, 0, 10, 10))


class OwnedPlate(PlateUnderTest):
    @property
    def plate_config(self) -> PlateConfig:
        return PlateConfig(screen=Screen(width=320, height=240), theme=THEME, gui=GuiDefaults(idle1=30, idle2=90))


def _jsonl(*objects) -> Mqtt:
    return Mqtt(
        "hasp/mqtt_name/command/jsonl", "\n".join(json.dumps(o, separators=(",", ":"), ensure_ascii=False) for o in objects)
    )


PAGE_1 = [
    {"page": 1, "id": 0, "bg_color": "#101010"},
    {
        "page": 1,
        "id": 1,
        "obj": "label",
        "x": 10,
        "y": 10,
        "w": 300,
        "h": 40,
        "text_font": 32,
        "text": "Desk",
        "text_color": "#FFFFFF",
    },
    {"page": 1, "id": 2, "obj": "label", "x": 10, "y": 60, "w": 145, "h": 170, "border_width": 1, "text_color": "#FFFFFF"},
    {"page": 1, "id": 3, "obj": "switch", "x": 165, "y": 60, "w": 145, "h": 170},
]
PAGE_2 = [
    {"page": 2, "id": 0, "bg_color": "#101010"},
    {"page": 2, "id": 1, "obj": "btn", "x": 0, "y": 0, "w": 160, "h": 120, "text": "Reboot"},
]


async def test_owned_pages_are_cleared_and_pushed_before_their_objects_are_bound(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    await simulator.ha.trigger_state_change("light.desk", "on")

    controller = await start_plate(
        OwnedPlate, pages=[page_at(1, TreePage), page_at(2, ExplicitPage), page_at(3, ExternalTreePage)]
    )

    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        GUI_DEFAULTS_HTTP,
        # page 1 (register_objects()' border_width of p1b2 is part of the pushed JSONL)
        Mqtt("hasp/mqtt_name/command/clearpage", 1),
        _jsonl(*PAGE_1),
        *[
            Mqtt("hasp/mqtt_name/command", c)
            for c in ["p1b2.text=12:00", "p1b2.text=12:00", "p1b3.val=1", "p1b3.enabled=True"]
        ],
        # page 2
        Mqtt("hasp/mqtt_name/command/clearpage", 2),
        _jsonl(*PAGE_2),
        # page 3: external, nothing pushed; the static property of its leaf is set on bind
        *[Mqtt("hasp/mqtt_name/command", c) for c in ["p3b10.text=12:00", "p3b10.text=12:00", "p3b10.mode=scroll"]],
        # navigation: swiping cycles through pages 1-3
        *[
            Mqtt("hasp/mqtt_name/command", c)
            for c in [
                "p1b0.prev=3",
                "p1b0.next=2",
                "p2b0.prev=1",
                "p2b0.next=3",
                "p3b0.prev=2",
                "p3b0.next=1",
            ]
        ],
        # first sync
        *[Mqtt("hasp/mqtt_name/command", c) for c in ["p1b2.text=12:00", "p3b10.text=12:00", "p3b10.mode=scroll"]],
    ]
    assert controller.plate_controller.rendered == {1: PAGE_1, 2: PAGE_2}

    # a click on an owned button
    await plate.send("state/p2b1", {"event": "up"})
    assert controller.plate_controller.pages[2].reboots == [True]


GUI_DEFAULTS_HTTP = Http("POST", "config", {"idle1": 60, "idle2": 120, "rotate": 1, "cursor": 0, "bckl": 32, "save": "gui"})


async def test_lwt_online_clears_and_pushes(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    await simulator.ha.trigger_state_change("light.desk", "on")
    await start_plate(OwnedPlate, pages=[page_at(1, TreePage), page_at(2, ExplicitPage)])
    plate.clear()

    await plate.send("LWT", "online")
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()

    # cleared: after a reboot, the plate's boot.cmd may have put objects from flash on the pages
    assert plate.traffic == [
        Mqtt("hasp/mqtt_name/command/clearpage", 1),
        _jsonl(*PAGE_1),
        Mqtt("hasp/mqtt_name/command/clearpage", 2),
        _jsonl(*PAGE_2),
        *[Mqtt("hasp/mqtt_name/command", c) for c in ["p1b0.prev=2", "p1b0.next=2", "p2b0.prev=1", "p2b0.next=1"]],
        # the sync after the push
        Mqtt("hasp/mqtt_name/command", "p1b2.text=12:00"),
    ]


async def test_no_navigation_without_owned_pages_or_when_switched_off(simulator, start_plate, plate: FakePlate):
    class NoWrapPlate(OwnedPlate):
        @property
        def plate_config(self) -> PlateConfig:
            return PlateConfig(screen=Screen(width=320, height=240), wrap_navigation=False)

    await start_plate(NoWrapPlate, pages=[page_at(1, ExplicitPage), page_at(2, ExplicitPage)])
    await start_plate(OwnedPlate, pages=[page_at(1, ExplicitPage)])
    await start_plate(OwnedPlate, pages=[page_at(0, ExplicitPage), page_at(1, ExternalTreePage)])

    assert not [m for m in plate.commands if ".prev=" in m or ".next=" in m]


async def test_mixed_page_fails_the_setup(simulator, load_plate, plate: FakePlate, caplog):
    controller = load_plate(OwnedPlate, pages=[page_at(1, MixedPage)])
    await simulator.start(controller)

    await simulator.advance(timedelta(seconds=1))

    assert "Page 1 mixes owned objects" in caplog.text
    assert not [m for m in plate.mqtt if "jsonl" in m[0]]


async def test_plate_config_overrides_the_device_config(simulator, start_plate, plate: FakePlate):
    controller = await start_plate(OwnedPlate, pages=[page_at(1, ExplicitPage)])
    plate_controller = controller.plate_controller
    assert plate_controller.screen == Screen(width=320, height=240)
    assert plate_controller.gui_defaults == GuiDefaults(idle1=30, idle2=90)
    plate.clear()

    await plate_controller.set_keep_awake(True)
    await plate_controller.set_keep_awake(False)

    assert Http("POST", "config", {"idle1": 30, "idle2": 90, "save": "gui"}) in plate.http


async def test_device_config_defaults(start_plate):
    controller = await start_plate(pages=[page_at(1, ExplicitPage)])

    # the test device's screen is 320x480, rotated
    assert controller.plate_controller.screen == Screen(width=480, height=320)
    assert controller.plate_controller.gui_defaults == GuiDefaults(idle1=60, idle2=120)


async def test_push_layout_of_external_page_sends_nothing(start_plate, plate: FakePlate):
    controller = await start_plate(pages=[page_at(1, ExternalTreePage)])
    plate.clear()

    await controller.plate_controller.push_layout(controller.plate_controller.pages[1])
    await controller.plate_controller.push_layout()

    assert plate.traffic == []


@pytest.mark.parametrize("count", [60])
async def test_large_pages_are_pushed_in_batches(start_plate, plate: FakePlate, count):
    class ManyLabels(PageController):
        async def register_objects(self):
            for i in range(count):
                await self.add_label(rect=Rect(0, i, 10, 1), text=f"Label number {i} with some text")

    await start_plate(OwnedPlate, pages=[page_at(1, ManyLabels)])

    payloads = [payload for topic, payload in plate.mqtt if topic.endswith("/jsonl")]
    assert len(payloads) > 1
    assert all(len(p.encode()) <= 1920 for p in payloads)
    assert sum(p.count("\n") + 1 for p in payloads) == count + 1


class ListPage(PageController):
    async def build_layout(self) -> Page:
        with Page() as page:
            with Column(gap=10):
                for entity in ["sensor.a", "sensor.b", "sensor.c"]:
                    Label(entity=entity, size=40, hidden=Bound(entity, lambda state: 1 if state is None else 0))
        return page


async def test_hidden_nodes_take_no_space_in_their_column(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.c", "1")
    controller = await start_plate(OwnedPlate, pages=[page_at(1, ListPage)])
    plate.clear()

    # c is the only one shown: it moved to the top (a and b keep the rect they had when they were hidden)
    ys = {o.obj_id: o.rect.y for o in controller.plate_controller.pages[1].objects.values() if o.obj_id}
    assert ys == {1: 0, 2: 0, 3: 0}
    assert controller.plate_controller.rendered[1][3]["y"] == 0

    await simulator.ha.trigger_state_change("sensor.a", "1")
    await plate.settle()

    ys = {o.obj_id: o.rect.y for o in controller.plate_controller.pages[1].objects.values() if o.obj_id}
    assert ys == {1: 0, 2: 0, 3: 50}
    assert "p1b3.y=50" in plate.commands
    assert [r["y"] for r in controller.plate_controller.rendered[1][1:]] == [0, 0, 50]


async def test_collapsing_before_the_first_layout_pass_changes_nothing_on_the_plate():
    with Page() as page:
        label = Label(size=40)
    await label.set_collapsed(True)
    await label.set_collapsed(True)

    assert label.collapsed and label.rect is None


async def _noop():
    pass


def _repeat_page(items: list, direction="column", panel=False):
    """A page with a list of labels (or panels with a label), one per value of `items`; `sensor.entry_<value>` is shown."""

    class RepeatPage(PageController):
        async def build_layout(self) -> Page:
            async def source():
                return list(items)

            async def item(value):
                if panel:
                    with Panel(size=40):
                        Label(entity=f"sensor.{value}")
                        Button(text=value, on_click=_noop)
                else:
                    Label(entity=f"sensor.{value}", size=40)

            with Page() as page:
                Repeat(source, item, trigger="sensor.trigger", direction=direction, gap=10)
            return page

    return RepeatPage


def _commands(plate: FakePlate):
    """The plain commands (`p1b2.y=0`, `p1b1.delete`) sent to the plate, without the JSONL."""
    return [c.removesuffix(" None") for c in plate.commands if not c.startswith("jsonl")]


async def test_repeat_follows_its_source(simulator, start_plate, plate: FakePlate):
    items = ["a", "b"]
    for name in "abc":
        await simulator.ha.trigger_state_change(f"sensor.{name}", name)
    controller = await start_plate(OwnedPlate, pages=[page_at(1, _repeat_page(items))])
    page = controller.plate_controller.pages[1]
    # the initial items are part of the pushed page
    assert [(o["id"], o["y"]) for o in controller.plate_controller.rendered[1][1:]] == [(1, 0), (2, 50)]
    plate.clear()

    # a is gone, c is new: c takes the freed id, b moves up
    items[:] = ["b", "c"]
    await simulator.ha.trigger_state_change("sensor.trigger", "1")
    await plate.settle()

    assert sorted(page.objects) == [1, 2]
    assert [(o["id"], o["y"]) for o in controller.plate_controller.rendered[1][1:]] == [(2, 0), (1, 50)]
    commands = _commands(plate)
    assert commands[:2] == ["p1b1.delete", "p1b2.y=0"]
    new_object = [json.loads(m[1]) for m in plate.mqtt if m[0].endswith("/jsonl")]
    assert [(o["id"], o["y"]) for o in new_object] == [(1, 50)]
    # c is bound: its text arrived
    assert "p1b1.text=c" in commands

    # the page pushed after a reconnect has the current items
    plate.clear()
    await plate.send("LWT", "online")
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    pushed = json.loads("[" + ",".join(m[1].replace("\n", ",") for m in plate.mqtt if m[0].endswith("/jsonl")) + "]")
    assert [(o["id"], o["y"]) for o in pushed[1:]] == [(2, 0), (1, 50)]


async def test_removed_items_stop_following_their_entities(simulator, start_plate, plate: FakePlate):
    items = ["a", "b"]
    await simulator.ha.trigger_state_change("sensor.a", "1")
    await simulator.ha.trigger_state_change("sensor.b", "1")
    await start_plate(OwnedPlate, pages=[page_at(1, _repeat_page(items, panel=True))])

    items[:] = ["b"]
    await simulator.ha.trigger_state_change("sensor.trigger", "1")
    await plate.settle()
    commands = _commands(plate)
    # only the panel is deleted: the plate deletes its label with it
    assert [c for c in commands if c.endswith(".delete")] == ["p1b1.delete"]

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.a", "2")
    await simulator.ha.trigger_state_change("sensor.b", "2")
    await plate.settle()
    assert _commands(plate) == ["p1b5.text=2"]


async def test_repeat_in_a_row_and_a_reordered_list(simulator, start_plate, plate: FakePlate):
    items = ["a", "b"]
    controller = await start_plate(OwnedPlate, pages=[page_at(1, _repeat_page(items, direction="row"))])
    plate.clear()

    items[:] = ["b", "a"]
    await simulator.ha.trigger_state_change("sensor.trigger", "1")
    await plate.settle()

    # nothing was created or deleted, the objects swapped places
    assert sorted(_commands(plate)) == ["p1b1.x=50", "p1b2.x=0"]


async def test_repeat_rejects_duplicate_keys_and_unknown_directions():
    async def source():
        return ["a", "a"]

    async def item(value):
        Label()

    with Page():
        repeat = Repeat(source, item, trigger="sensor.trigger")
        with pytest.raises(ValueError, match="Invalid direction"):
            Repeat(source, item, trigger="sensor.trigger", direction="diagonal")

    with pytest.raises(ValueError, match="not unique"):
        await repeat.reconcile()


async def test_nested_repeats_are_removed_with_their_item(simulator, start_plate, plate: FakePlate):
    outer = ["a", "b"]
    extra = {}

    class NestedPage(PageController):
        async def build_layout(self) -> Page:
            async def inner_item(value):
                Label(text=value, size=20)

            async def outer_item(value):
                async def inner_source():
                    return [f"{value}1", f"{value}2", *extra.get(value, [])]

                with Panel(size=60):
                    Repeat(inner_source, inner_item, trigger="sensor.trigger")

            async def outer_source():
                return list(outer)

            with Page() as page:
                Repeat(outer_source, outer_item, trigger="sensor.trigger")
            return page

    controller = await start_plate(OwnedPlate, pages=[page_at(1, NestedPage)])
    page = controller.plate_controller.pages[1]
    assert len(page.objects) == 6

    plate.clear()
    outer[:] = ["b", "c"]
    await simulator.ha.trigger_state_change("sensor.trigger", "1")
    await plate.settle()

    assert len(page.objects) == 6
    pushed = [json.loads(line) for m in plate.mqtt if m[0].endswith("/jsonl") for line in m[1].split("\n")]
    assert [o["text"] for o in pushed if "text" in o] == ["c1", "c2"]

    # an item added to a list inside of an item is created inside of that item's panel
    plate.clear()
    extra["b"] = ["b3"]
    await simulator.ha.trigger_state_change("sensor.trigger", "2")
    await plate.settle()

    pushed = [json.loads(line) for m in plate.mqtt if m[0].endswith("/jsonl") for line in m[1].split("\n")]
    assert [(o["text"], o["parentid"]) for o in pushed] == [("b3", 4)]
