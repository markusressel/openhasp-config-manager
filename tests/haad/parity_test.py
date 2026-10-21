"""
Parity (README §8): the same page declared in all four combinations of §3 (tree or explicit calls, layout in code or on
flash) has the same bindings, and the two code-layout variants push the same JSONL.
"""
import pytest

from openhasp_config_manager.haad.layout.components import Label, Page, Row, Switch
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.page import PageController
from tests.haad.conftest import page_at
from tests.haad.fakes import FakePlate
from tests.haad.owned_plate_test import OwnedPlate

CO2_BORDER = Bound("sensor.co2", lambda x: 3 if x is not None and float(x) > 1000 else 0)


def _co2_text(x):
    return f"{int(float(x))}ppm"


class OwnedTree(PageController):
    async def build_layout(self) -> Page:
        with Page() as page:
            with Row(gap=8, padding=8):
                Label(entity="sensor.co2", text=_co2_text, border_width=CO2_BORDER, weight=2)
                Switch(entity="light.desk")
        return page


class OwnedCalls(PageController):
    async def register_objects(self):
        # the rects the tree computes for a 320x240 screen
        await self.add_label(entity="sensor.co2", text=_co2_text, rect=Rect(8, 8, 197, 224), props={"border_width": CO2_BORDER})
        await self.add_switch(entity="light.desk", rect=Rect(213, 8, 99, 224))


class ExternalTree(PageController):
    async def build_layout(self) -> Page:
        with Page(external=True) as page:
            Label(obj_id=1, entity="sensor.co2", text=_co2_text, border_width=CO2_BORDER)
            Switch(obj_id=2, entity="light.desk")
        return page


class ExternalCalls(PageController):
    async def register_objects(self):
        await self.add_label(obj_id=1, entity="sensor.co2", text=_co2_text, props={"border_width": CO2_BORDER})
        await self.add_switch(obj_id=2, entity="light.desk")


def _bindings(page: PageController) -> list:
    return [(o.obj_id, o.obj_type, o.static_props, list(o.bound_props)) for o in page.objects.values()]


async def _start(simulator, start_plate, plate: FakePlate, page_cls):
    await simulator.ha.trigger_state_change("sensor.co2", "1234")
    await simulator.ha.trigger_state_change("light.desk", "on")
    controller = await start_plate(OwnedPlate, pages=[page_at(1, page_cls)])
    page = controller.plate_controller.pages[1]
    jsonl = [payload for topic, payload in plate.mqtt if topic.endswith("/jsonl")]
    commands = [c for c in plate.commands if c.startswith("p1b") and not c.startswith("p1b0")]
    return page, jsonl, commands, sorted(page.state_updater._registered_objects)


@pytest.mark.parametrize("owned_cls, external_cls", [(OwnedTree, ExternalTree), (OwnedCalls, ExternalCalls)])
async def test_owned_and_external_variants_bind_the_same(simulator, start_plate, plate: FakePlate, owned_cls, external_cls):
    owned, owned_jsonl, owned_commands, owned_entries = await _start(simulator, start_plate, plate, owned_cls)
    plate.clear()
    external, external_jsonl, external_commands, external_entries = await _start(simulator, start_plate, plate, external_cls)

    assert owned_jsonl and not external_jsonl
    assert [(i, t, b) for i, t, _, b in _bindings(owned)] == [(i, t, b) for i, t, _, b in _bindings(external)]
    assert owned_entries == external_entries
    assert owned_commands == external_commands == [
        "p1b1.text=1234ppm", "p1b1.text=1234ppm", "p1b1.border_width=3", "p1b2.val=1", "p1b2.enabled=True",
        # first sync
        "p1b1.text=1234ppm", "p1b1.border_width=3",
    ]


async def test_tree_and_calls_push_the_same_jsonl(simulator, start_plate, plate: FakePlate):
    _, tree_jsonl, _, _ = await _start(simulator, start_plate, plate, OwnedTree)
    plate.clear()
    _, calls_jsonl, _, _ = await _start(simulator, start_plate, plate, OwnedCalls)

    assert tree_jsonl == calls_jsonl
