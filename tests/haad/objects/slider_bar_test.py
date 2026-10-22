import pytest

from openhasp_config_manager.haad.objects.slider import SliderObjectController
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


async def test_slider_without_binding_sends_nothing(page: PageController, plate: FakePlate):
    slider = await page.add_slider(obj_id=40)

    await slider.init()

    assert plate.commands == []
    assert page.state_updater._registered_objects == {}


async def test_slider_syncs_entity_state_but_does_not_follow_it(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.volume", "45%")
    slider = await page.add_slider(obj_id=40, entity="sensor.volume")

    await slider.init()
    assert list(page.state_updater._registered_objects) == ["slider:p1b40:sensor.volume"]
    assert plate.commands == ["p1b40.val=45"]

    # no reaction to entity changes, only syncs
    plate.clear()
    await simulator.ha.trigger_state_change("sensor.volume", "12.7")
    await plate.settle()
    assert plate.commands == []

    await page.plate.sync()
    assert plate.commands == ["p1b40.val=12"]


async def test_slider_with_get_state(page: PageController, plate: FakePlate):
    async def get_state():
        return 7

    slider = await page.add_slider(obj_id=40, get_state=get_state)

    await slider.init()

    assert list(page.state_updater._registered_objects) == ["slider:p1b40:None"]
    assert plate.commands == ["p1b40.val=7"]


async def test_slider_events(page: PageController, plate: FakePlate):
    changed, released = [], []

    async def on_changed(value):
        changed.append(value)

    async def on_released(value):
        released.append(value)

    async def get_state():
        return 0

    slider = await page.add_slider(obj_id=40, get_state=get_state, on_changed=on_changed, on_released=on_released)
    await slider.init()

    await plate.send("state/p1b40", {"event": "down", "val": 1})
    await plate.send("state/p1b40", {"event": "changed", "val": 2})
    await plate.send("state/p1b40", {"event": "up", "val": 3})

    assert changed == [2]
    assert released == [3]


async def test_slider_events_without_callbacks(page: PageController, plate: FakePlate):
    async def get_state():
        return 0

    slider = await page.add_slider(obj_id=40, get_state=get_state)
    await slider.init()

    await plate.send("state/p1b40", {"event": "changed", "val": 2})
    await plate.send("state/p1b40", {"event": "up", "val": 3})

    assert plate.subscribed


async def test_slider_state_getter_without_source_returns_none(simulator, page: PageController, caplog):
    """Unreachable through init(): without entity and get_state the getter returns None, which the transform rejects."""
    await simulator.ha.trigger_state_change("sensor.volume", "1")
    slider = await page.add_slider(obj_id=40, entity="sensor.volume")
    await slider.init()
    slider._entity_id = None

    await page.state_updater.sync()

    assert "Failed to set state 'None'" in caplog.text


async def test_slider_property_setters(page: PageController, plate: FakePlate):
    slider = await page.add_slider(obj_id=40)

    await slider.set_value(10)
    await slider.set_value("10")
    await slider.set_min_max(0, 100)
    await slider.set_min_allowed(5)

    assert plate.commands == ["p1b40.val=10", "p1b40.min=0", "p1b40.max=100", "p1b40.start_value=5"]


async def test_bar_without_binding_sends_nothing(page: PageController, plate: FakePlate):
    bar = await page.add_bar(obj_id=28)

    await bar.init()

    assert plate.commands == []
    assert page.state_updater._registered_objects == {}


async def test_bar_follows_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.progress", "42.9 %")
    bar = await page.add_bar(obj_id=28, entity="sensor.progress")

    await bar.init()
    assert list(page.state_updater._registered_objects) == ["progress:p1b28:sensor.progress"]
    # sync and immediate reaction, the second one de-duplicated
    assert plate.commands == ["p1b28.enabled=True", "p1b28.val=42"]

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.progress", "50")
    await plate.settle()
    assert plate.commands == ["p1b28.val=50"]


async def test_bar_with_unavailable_entity_fails_init(simulator, page: PageController, plate: FakePlate):
    """
    The sync disables the bar; the immediate reaction gets None, enables the bar and fails in the transform. The error
    propagates out of init() (and with it out of the plate setup).
    """
    await simulator.ha.trigger_state_change("sensor.progress", "unavailable")
    bar = await page.add_bar(obj_id=28, entity="sensor.progress")

    with pytest.raises(TypeError, match="float\\(\\) argument must be a string or a real number, not 'NoneType'"):
        await bar.init()

    assert plate.commands == ["p1b28.enabled=False", "p1b28.enabled=True"]


async def test_bar_with_get_state_and_transform(page: PageController, plate: FakePlate):
    async def get_state():
        return "abc"

    bar = await page.add_bar(obj_id=28, get_state=get_state, transform_value=lambda x: len(x))

    await bar.init()

    assert list(page.state_updater._registered_objects) == ["progress:p1b28:None"]
    assert plate.commands == ["p1b28.enabled=True", "p1b28.val=3"]


async def test_bar_state_getter_without_source_returns_none(simulator, page: PageController, caplog):
    """Unreachable through init(): without entity and get_state the getter returns None, which the transform rejects."""
    await simulator.ha.trigger_state_change("sensor.progress", "1")
    bar = await page.add_bar(obj_id=28, entity="sensor.progress")
    await bar.init()
    bar._entity_id = None

    await page.state_updater.sync()

    assert "Failed to set state 'None'" in caplog.text


async def test_bar_property_setters(page: PageController, plate: FakePlate):
    bar = await page.add_bar(obj_id=28)

    await bar.set_progress(10)
    await bar.set_progress("10")
    await bar.set_min_max(0, 200)

    assert plate.commands == ["p1b28.val=10", "p1b28.min=0", "p1b28.max=200"]


async def test_slider_with_transform(page: PageController, plate: FakePlate):
    """add_slider() has no transform_value, only the object controller has."""
    slider = SliderObjectController(
        controller=page.controller,
        client=page.client,
        state_updater=page.state_updater,
        page=1,
        obj_id=40,
        transform_value=lambda x: len(x),
    )

    await slider.set_value("abc")

    assert plate.commands == ["p1b40.val=3"]
