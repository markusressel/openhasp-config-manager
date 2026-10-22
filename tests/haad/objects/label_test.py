from openhasp_config_manager.haad.objects.label import LabelObjectController
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


async def test_label_without_binding_sends_nothing(page: PageController, plate: FakePlate):
    label = await page.add_label(obj_id=10)

    await label.init()

    assert plate.commands == []
    assert page.state_updater._registered_objects == {}


async def test_label_shows_entity_state(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    label = await page.add_label(obj_id=10, entity="sensor.time")

    await label.init()
    # once from the StateUpdater sync, once from react_to(immediately=True): set_text() is not de-duplicated
    assert plate.commands == ["p1b10.text=12:00", "p1b10.text=12:00"]
    assert list(page.state_updater._registered_objects) == ["label:p1b10:sensor.time"]

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.time", "12:01")
    await plate.settle()
    assert plate.commands == ["p1b10.text=12:01"]


async def test_label_converts_state(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.co2", "1234.5")
    label = await page.add_label(obj_id=12, entity="sensor.co2", text=lambda x: f"{int(float(x))}ppm")

    await label.init()

    assert plate.commands == ["p1b12.text=1234ppm", "p1b12.text=1234ppm"]


async def test_label_with_unknown_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.time", "unknown")
    label = await page.add_label(obj_id=10, entity="sensor.time")

    await label.init()
    # the sync shows "-" for unknown, the immediate reaction gets None from haad and shows "None"
    assert plate.commands == ["p1b10.text=-", "p1b10.text=None"]

    # haad's triggers filter changes to unknown/unavailable: the label keeps the last value
    plate.clear()
    await simulator.ha.trigger_state_change("sensor.time", "5")
    await simulator.ha.trigger_state_change("sensor.time", "unavailable")
    await plate.settle()
    assert plate.commands == ["p1b10.text=5"]

    # a sync (e.g. after a reconnect) shows "-"
    plate.clear()
    await page.state_updater.sync()
    assert plate.commands == ["p1b10.text=-"]


async def test_label_converter_gets_dash_for_unavailable(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.co2", "unavailable")
    label = await page.add_label(obj_id=12, entity="sensor.co2", text=lambda x: f"[{x}]")

    await label.init()

    assert plate.commands == ["p1b12.text=[-]", "p1b12.text=[None]"]


async def test_label_shows_none_from_get_state(page: PageController, plate: FakePlate):
    """add_label's default `text` is str(), so LabelObjectController's own default ("-" for None) never applies."""

    async def get_state():
        return None

    label = await page.add_label(obj_id=10, get_state=get_state)

    await label.init()

    assert plate.commands == ["p1b10.text=None"]
    assert list(page.state_updater._registered_objects) == ["label:p1b10:None"]


async def test_label_object_default_converter_shows_dash_for_none(page: PageController, plate: FakePlate):
    async def get_state():
        return None

    label = LabelObjectController(
        controller=page.controller,
        client=page.client,
        state_updater=page.state_updater,
        page=1,
        obj_id=10,
        get_state=get_state,
    )

    await label.init()

    assert plate.commands == ["p1b10.text=-"]


async def test_label_custom_converter_gets_none(page: PageController, plate: FakePlate):
    async def get_state():
        return None

    label = await page.add_label(obj_id=10, get_state=get_state, text=lambda x: f"<{x}>")

    await label.init()

    assert plate.commands == ["p1b10.text=<None>"]


async def test_label_shows_attribute(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("climate.bath", "heat", {"current_temperature": 21.5})
    label = await page.add_label(
        obj_id=12, entity="climate.bath", attribute="current_temperature", text=lambda x: f"{float(x)}°C"
    )

    await label.init()
    assert plate.commands == ["p1b12.text=21.5°C", "p1b12.text=21.5°C"]

    plate.clear()
    await simulator.ha.trigger_state_change("climate.bath", "heat", {"current_temperature": 22})
    await plate.settle()
    assert plate.commands == ["p1b12.text=22.0°C"]


async def test_label_with_get_state_and_entity_list(simulator, page: PageController, plate: FakePlate):
    """Like the media page: the entities are only triggers, the text comes from get_state."""
    await simulator.ha.trigger_state_change("media_player.a", "playing", {"media_artist": "A"})
    await simulator.ha.trigger_state_change("media_player.b", "idle", {})
    calls = []

    async def get_artist():
        calls.append("get")
        return "Artist"

    label = await page.add_label(obj_id=25, entity=["media_player.a", "media_player.b"], attribute="all", get_state=get_artist)

    await label.init()
    assert list(page.state_updater._registered_objects) == ["label:p1b25:media_player.a,media_player.b"]
    # sync + one immediate reaction per entity
    assert plate.commands == ["p1b25.text=Artist"] * 3
    # the sync calls get_state twice: once for the state, once more in the state change handler
    assert calls == ["get"] * 4

    plate.clear()
    await simulator.ha.trigger_state_change("media_player.b", "playing", {"media_artist": "B"})
    await plate.settle()
    assert plate.commands == ["p1b25.text=Artist"]


async def test_label_with_entity_list_syncs_first_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("light.a", "on")
    await simulator.ha.trigger_state_change("light.b", "off")
    label = await page.add_label(obj_id=10, entity=["light.a", "light.b"])

    await label.init()

    # sync (first entity), then one immediate reaction per entity
    assert plate.commands == ["p1b10.text=on", "p1b10.text=on", "p1b10.text=off"]


async def test_label_with_entity_list_and_attribute_syncs_first_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("light.a", "on", {"brightness": 10})
    await simulator.ha.trigger_state_change("light.b", "on", {"brightness": 20})
    label = await page.add_label(obj_id=10, entity=["light.a", "light.b"], attribute="brightness")

    await label.init()

    assert plate.commands == ["p1b10.text=10", "p1b10.text=10", "p1b10.text=20"]


async def test_label_property_setters(page: PageController, plate: FakePlate):
    label = await page.add_label(obj_id=10)

    await label.set_text("abc")
    await label.set_text("abc")
    await label.set_color("#FF0000")
    await label.set_color("#FF0000")
    await label.set_mode("scroll")
    await label.set_border_width(3)
    await label.set_border_width()

    # set_text() is not de-duplicated, the others are
    assert plate.commands == [
        "p1b10.text=abc",
        "p1b10.text=abc",
        "p1b10.text_color=#FF0000",
        "p1b10.mode=scroll",
        "p1b10.border_width=3",
        "p1b10.border_width=0",
    ]
