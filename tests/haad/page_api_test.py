"""The additions of the code-defined layouts to the page API (README §4.4, §4.8): props, Bound, trigger=, ids, owned objects."""

from datetime import timedelta

import pytest

from haad.hass.entity import HAEntity
from haad.triggers import Trigger
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.objects.generic import GenericObjectController
from openhasp_config_manager.haad.page import MAX_OBJ_ID, PageController
from tests.haad.conftest import PLACEHOLDER_ID
from tests.haad.fakes import FakePlate

RECT = Rect(0, 0, 10, 10)


async def test_props_of_external_objects_are_set_on_bind_and_every_sync(page: PageController, plate: FakePlate):
    label = await page.add_label(obj_id=26, props={"mode": "scroll", "text_color": "#FFFFFF"})

    await page.initialize_objects()
    assert plate.commands == ["p1b26.mode=scroll", "p1b26.text_color=#FFFFFF"]

    plate.clear()
    await page.plate.sync()
    assert plate.commands == ["p1b26.mode=scroll", "p1b26.text_color=#FFFFFF"]
    assert label.static_props == {"mode": "scroll", "text_color": "#FFFFFF"}


async def test_props_of_owned_objects_are_not_sent_on_bind(page: PageController, plate: FakePlate):
    """Owned objects get their static properties with the pushed JSONL."""
    label = await page.add_label(rect=RECT, props={"mode": "scroll"})

    await label.init()
    await label.bind()

    assert plate.commands == []


async def test_static_text(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.start", "x")
    static = await page.add_label(obj_id=29, text="Elapsed:")
    bound = await page.add_label(obj_id=30, entity="sensor.start", text="Remaining:")
    owned = await page.add_label(rect=RECT, text="Owned")

    for label in [static, bound, owned]:
        await label.init()
        await label.bind()

    assert static.props == {"text": "Elapsed:"}
    assert owned.props == {"text": "Owned"}
    # external: from the props; the bound label additionally from its (constant) converter
    assert plate.commands == ["p1b29.text=Elapsed:", "p1b30.text=Remaining:", "p1b30.text=Remaining:", "p1b30.text=Remaining:"]


async def test_bound_property_follows_its_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.co2", "800")
    label = await page.add_label(
        obj_id=12,
        props={"border_width": Bound(HAEntity("sensor.co2"), lambda x: 3 if x is not None and float(x) > 1000 else 0)},
    )

    await label.init()
    await label.bind()
    assert plate.commands == ["p1b12.border_width=0"]
    assert label.static_props == {}

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.co2", "1200")
    await plate.settle()
    assert plate.commands == ["p1b12.border_width=3"]

    # restored by every sync
    plate.clear()
    await page.plate.sync()
    assert plate.commands == ["p1b12.border_width=3"]


async def test_bound_property_gets_none_for_unavailable_entities(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("number.target", "unavailable")
    label = await page.add_label(obj_id=12, props={"hidden": Bound("number.target", lambda t: t is None)})

    await label.init()
    await label.bind()

    assert plate.commands == ["p1b12.hidden=True"]


async def test_bound_property_without_converter(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("input_text.color", "#123456")
    label = await page.add_label(obj_id=12, props={"text_color": Bound("input_text.color")})

    await label.init()
    await label.bind()

    assert plate.commands == ["p1b12.text_color=#123456"]


async def test_bound_property_with_get_state_on_any_trigger(simulator, page: PageController, plate: FakePlate):
    ticks = []

    async def get_state():
        ticks.append(1)
        return len(ticks)

    bar = await page.add_bar(
        obj_id=28, props={"max": Bound(Trigger.Time.every(interval=timedelta(seconds=1)), get_state=get_state)}
    )

    await bar.init()
    await bar.bind()
    await simulator.advance(timedelta(seconds=2))
    await plate.settle()

    assert plate.commands == ["p1b28.max=1", "p1b28.max=2", "p1b28.max=3"]


def test_bound_on_a_non_entity_trigger_needs_get_state():
    with pytest.raises(ValueError, match="needs get_state"):
        Bound(Trigger.Time.every(interval=timedelta(seconds=1)), lambda x: x)


async def test_trigger_refreshes_the_object(simulator, page: PageController, plate: FakePlate):
    seconds = []

    async def elapsed():
        seconds.append(1)
        return f"{len(seconds)}s"

    label = await page.add_label(obj_id=30, get_state=elapsed, trigger=Trigger.Time.every(interval=timedelta(seconds=1)))

    await label.init()
    await label.bind()
    await simulator.advance(timedelta(seconds=2))
    await plate.settle()

    # the label's sync calls get_state twice (see label_test.py)
    assert plate.commands == ["p1b30.text=2s", "p1b30.text=4s", "p1b30.text=6s"]


async def test_auto_ids_skip_explicit_and_reserved_ids(page: PageController):
    page.reserve_ids([3])
    first = await page.add_label(rect=RECT)
    explicit = await page.add_label(obj_id=2, rect=RECT)
    second = await page.add_label(rect=RECT)
    third = await page.add_switch(rect=RECT)

    assert [first.obj_id, explicit.obj_id, second.obj_id, third.obj_id] == [1, 2, 4, 5]


async def test_explicit_id_taken_by_an_auto_id_raises(page: PageController):
    await page.add_label(rect=RECT)

    with pytest.raises(ValueError, match="Object with id 1 already exists on page 1"):
        await page.add_label(obj_id=1, rect=RECT)


async def test_object_without_id_and_rect_raises(page: PageController):
    with pytest.raises(ValueError, match="needs an obj_id \\(external object\\) or a rect \\(owned object\\)"):
        await page.add_switch(entity="light.desk")


async def test_more_than_254_objects_raise(page: PageController):
    for _ in range(MAX_OBJ_ID - 1):  # one id is taken by the placeholder
        await page.add_label(rect=RECT)

    with pytest.raises(ValueError, match="Page 1 has more than 254 objects"):
        await page.add_label(rect=RECT)


async def test_owned_objects_and_pages(page: PageController):
    assert not page.owned
    external = await page.add_label(obj_id=10)
    owned = await page.add_object("arc", rect=RECT, props={"min": 0})

    assert not external.owned and external.rect is None
    assert owned.owned and owned.rect == RECT
    assert page.owned
    assert isinstance(owned, GenericObjectController)
    assert owned.obj_type == "arc"
    assert owned.object_id == "p1b1"
    await owned.init()


async def test_obj_types(page: PageController):
    objects = [
        await page.add_label(rect=RECT),
        await page.add_button(rect=RECT),
        await page.add_scene_button(rect=RECT, scene="work"),
        await page.add_switch(rect=RECT),
        await page.add_slider(rect=RECT),
        await page.add_bar(rect=RECT),
        await page.add_image(rect=RECT),
    ]

    assert [o.obj_type for o in objects] == ["label", "btn", "btn", "switch", "slider", "bar", "img"]
    assert page.objects[PLACEHOLDER_ID].obj_type == "label"


async def test_button_texts(page: PageController):
    button = await page.add_button(rect=RECT, text="Pause", props={"align": "center"})
    scene = await page.add_scene_button(rect=RECT, scene="work", text="Work", props={"text": "wins"})

    assert button.props == {"align": "center", "text": "Pause"}
    assert scene.props == {"text": "wins"}


async def test_scene_button_needs_a_scene(page: PageController):
    with pytest.raises(ValueError, match="needs a scene"):
        await page.add_scene_button(rect=RECT)


async def test_button_without_on_click_does_not_listen(page: PageController, plate: FakePlate):
    button = await page.add_button(obj_id=20)

    await button.init()
    await plate.send("state/p1b20", {"event": "up"})

    assert plate.subscribed


async def test_parents(page: PageController):
    panel = await page.add_object("obj", rect=RECT)
    child = await page.add_label(rect=Rect(1, 1, 5, 5), parent=panel)
    external = await page.add_label(obj_id=50)

    assert child.parent is panel
    with pytest.raises(ValueError, match="only owned objects can be placed in an owned parent"):
        await page.add_label(obj_id=51, parent=panel)
    with pytest.raises(ValueError, match="only owned objects can be placed in an owned parent"):
        await page.add_label(rect=RECT, parent=external)


async def test_declaration_site(page: PageController):
    label = await page.add_label(rect=RECT)

    assert label.declaration.startswith("page_api_test.py:")


async def test_build_layout_default(page: PageController):
    assert await page.build_layout() is None
