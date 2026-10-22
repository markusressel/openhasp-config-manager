import pytest

from openhasp_config_manager.haad.page import PageController
from tests.haad.conftest import PlateUnderTest, page_at
from tests.haad.fakes import FakePlate


async def test_switch_without_binding_sends_nothing(page: PageController, plate: FakePlate):
    switch = await page.add_switch(obj_id=22)

    await switch.init()

    assert plate.commands == []
    assert page.state_updater._registered_objects == {}


async def test_switch_follows_entity(simulator, page: PageController, plate: FakePlate, caplog):
    await simulator.ha.trigger_state_change("light.desk", "on")
    switch = await page.add_switch(obj_id=22, entity="light.desk")

    await switch.init()
    # the StateUpdater sync fails (it passes a bool to a handler that expects a str), the immediate reaction sets the switch
    assert list(page.state_updater._registered_objects) == ["switch:p1b22:light.desk"]
    assert "Failed to set state 'True': 'bool' object has no attribute 'lower'" in caplog.text
    assert plate.commands == ["p1b22.val=1", "p1b22.enabled=True"]

    plate.clear()
    await simulator.ha.trigger_state_change("light.desk", "off")
    await simulator.ha.trigger_state_change("light.desk", "OFF")
    await simulator.ha.trigger_state_change("light.desk", "dimmed")
    await simulator.ha.trigger_state_change("light.desk", "ON")
    await plate.settle()
    assert plate.commands == [
        "p1b22.val=0",
        # "OFF": no change
        "p1b22.enabled=False",
        "p1b22.val=1",
        "p1b22.enabled=True",
    ]


async def test_switch_with_unknown_entity_fails_init(simulator, page: PageController, plate: FakePlate):
    """
    The immediate reaction gets None for an unknown entity and fails on it. The error propagates out of init() (and with
    it out of the plate setup).
    """
    await simulator.ha.trigger_state_change("light.desk", "unknown")
    switch = await page.add_switch(obj_id=22, entity="light.desk")

    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'lower'"):
        await switch.init()

    assert plate.commands == []


async def test_switch_with_get_state_never_shows_a_state(page: PageController, plate: FakePlate, caplog):
    """get_state returns a bool, which the StateUpdater passes to the str handler: the sync fails, nothing is sent."""

    async def get_state():
        return True

    switch = await page.add_switch(obj_id=22, get_state=get_state)

    await switch.init()

    assert list(page.state_updater._registered_objects) == ["switch:p1b22:None"]
    assert plate.commands == []
    assert "'bool' object has no attribute 'lower'" in caplog.text


async def test_switch_with_entity_list_fails_init(simulator, page: PageController, plate: FakePlate, caplog):
    """
    Like the desk light strip on the Markus page: a list of entities. The sync can't read the state of a list, and the
    immediate reaction gets None and fails, which propagates out of init().
    """
    await simulator.ha.trigger_state_change("light.a", "on")
    await simulator.ha.trigger_state_change("light.b", "off")
    switch = await page.add_switch(obj_id=29, entity=["light.a", "light.b"])

    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'lower'"):
        await switch.init()

    assert list(page.state_updater._registered_objects) == ["switch:p1b29:['light.a', 'light.b']"]
    assert "Failed to retrieve current state: cannot use 'list' as a dict key" in caplog.text
    assert plate.commands == []


async def test_switch_click_fails_and_drops_the_mqtt_connection(simulator, page: PageController, plate: FakePlate, caplog):
    """HaadController has no get_entity(): toggling raises inside the MQTT message handler, which ends the connection."""
    await simulator.ha.trigger_state_change("light.desk", "on")
    switch = await page.add_switch(obj_id=22, entity="light.desk")
    await switch.init()

    await plate.send("state/p1b22", {"event": "changed", "val": 0})
    assert plate.subscribed

    await plate.send("state/p1b22", {"event": "up", "val": 0})

    assert "object has no attribute 'get_entity'" in caplog.text
    assert not plate.subscribed
    assert simulator.ha.called_services == []


async def test_switch_click_without_entity_does_nothing(simulator, page: PageController, plate: FakePlate):
    async def get_state():
        return False

    switch = await page.add_switch(obj_id=22, get_state=get_state)
    await switch.init()

    await plate.send("state/p1b22", {"event": "up", "val": 1})

    assert plate.subscribed
    assert simulator.ha.called_services == []


async def test_switch_state_getter_without_source_raises(simulator, page: PageController, caplog):
    """Unreachable through init(), which needs an entity or get_state: the getter raises without either."""
    await simulator.ha.trigger_state_change("light.desk", "on")
    switch = await page.add_switch(obj_id=22, entity="light.desk")
    await switch.init()
    switch._entity_id = None

    await page.state_updater.sync()

    assert "Failed to retrieve current state: No method to get state for this switch object" in caplog.text


async def test_switch_property_setters(page: PageController, plate: FakePlate):
    switch = await page.add_switch(obj_id=22)

    await switch.set_indicator_color("#FF0000")
    await switch.set_knob_color("#00FF00")
    await switch.set_knob_corner_radius(5)
    await switch.set_knob_corner_radius()

    assert plate.commands == [
        "p1b22.bg_color10=#FF0000",
        "p1b22.bg_color20=#00FF00",
        "p1b22.radius20=5",
        "p1b22.radius20=0",
    ]


async def test_switch_click_toggles_with_appdaemon_api(simulator, start_plate, plate: FakePlate):
    """What the click does with a controller that has AppDaemon's get_entity()/call_service() (HaadController has neither)."""
    calls = []

    class _Entity:
        entity_id = "light.desk"
        entity_name = "desk"

    class AppDaemonLikePlate(PlateUnderTest):
        def get_entity(self, entity):
            calls.append(("get_entity", entity))
            return _Entity()

        async def call_service(self, service, **kwargs):
            calls.append((service, kwargs))

    await simulator.ha.trigger_state_change("light.desk", "on")
    controller = await start_plate(AppDaemonLikePlate, pages=[page_at(1)])
    switch = await controller.plate_controller.pages[1].add_switch(obj_id=22, entity="light.desk")
    await switch.init()

    await plate.send("state/p1b22", {"event": "up", "val": 0})

    assert calls == [("get_entity", "light.desk"), ("homeassistant/switch", {"entity_id": "light.desk"})]
    assert plate.subscribed
