"""Plates with code-defined (owned) pages: render, push, re-push on LWT online, navigation (README §5)."""
import json
from datetime import timedelta

import pytest

from openhasp_config_manager.haad.layout.components import Column, Label, Page, Row, Switch
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import GuiDefaults, PlateBehavior, PlateConfig, Screen
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
    return Mqtt("hasp/mqtt_name/command/jsonl", "\n".join(json.dumps(o, separators=(",", ":"), ensure_ascii=False) for o in objects))


PAGE_1 = [
    {"page": 1, "id": 0, "bg_color": "#101010"},
    {"page": 1, "id": 1, "obj": "label", "x": 10, "y": 10, "w": 300, "h": 40, "text_font": 32, "text": "Desk", "text_color": "#FFFFFF"},
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

    controller = await start_plate(OwnedPlate, pages=[page_at(1, TreePage), page_at(2, ExplicitPage), page_at(3, ExternalTreePage)])

    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        GUI_DEFAULTS_HTTP,
        # page 1 (register_objects()' border_width of p1b2 is part of the pushed JSONL)
        Mqtt("hasp/mqtt_name/command/clearpage", 1),
        _jsonl(*PAGE_1),
        *[Mqtt("hasp/mqtt_name/command", c) for c in ["p1b2.text=12:00", "p1b2.text=12:00", "p1b3.val=1", "p1b3.enabled=True"]],
        # page 2
        Mqtt("hasp/mqtt_name/command/clearpage", 2),
        _jsonl(*PAGE_2),
        # page 3: external, nothing pushed; the static property of its leaf is set on bind
        *[Mqtt("hasp/mqtt_name/command", c) for c in ["p3b10.text=12:00", "p3b10.text=12:00", "p3b10.mode=scroll"]],
        # navigation: swiping cycles through pages 1-3
        *[Mqtt("hasp/mqtt_name/command", c) for c in [
            "p1b0.prev=3", "p1b0.next=2", "p2b0.prev=1", "p2b0.next=3", "p3b0.prev=2", "p3b0.next=1",
        ]],
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
    page = plate_controller.pages[1]
    assert plate_controller.screen == Screen(width=320, height=240)
    assert plate_controller.gui_defaults == GuiDefaults(idle1=30, idle2=90)
    plate.clear()

    await page.request_plate_behavior(PlateBehavior.ALWAYS_ON_DISPLAY)
    await page.drop_plate_behavior(PlateBehavior.ALWAYS_ON_DISPLAY)

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
