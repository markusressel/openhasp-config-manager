import asyncio

import pytest

from openhasp_config_manager.haad import util_openhasp
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


async def test_listen_event_until_cancelled(page: PageController, plate: FakePlate):
    events = []

    async def callback(topic, payload):
        events.append((topic, payload))

    task = await util_openhasp.listen_event(controller=page.controller, client=page.client, path="state/x", callback=callback)
    await plate.send("state/x", "1")
    await plate.send("state/y", "2")

    task.cancel()
    await plate.settle()
    await plate.send("state/x", "3")

    assert events == [("hasp/mqtt_name/state/x", b"1")]


async def test_listen_state_parses_json_and_is_never_cancelled(page: PageController, plate: FakePlate):
    """
    OpenHaspClient.listen_state() subscribes a wrapper of the callback, so cancelling the task (which unsubscribes the
    callback itself) leaves the subscription in place.
    """
    events = []

    async def callback(topic, payload):
        events.append((topic, payload))

    task = await util_openhasp.listen_state(controller=page.controller, client=page.client, obj="p1b2", callback=callback)
    await plate.send("state/p1b2", {"event": "up"})

    task.cancel()
    await plate.settle()
    await plate.send("state/p1b2", {"event": "down"})

    assert events == [("hasp/mqtt_name/state/p1b2", {"event": "up"}), ("hasp/mqtt_name/state/p1b2", {"event": "down"})]


@pytest.mark.parametrize("params, payload", [
    ("idle 10", "idle 10"),
    (["a", "b"], "a b"),
    ({"idle1": 10}, '{"idle1": 10}'),
])
async def test_config_publishes_through_home_assistant(simulator, page: PageController, params, payload):
    await util_openhasp.config(controller=page.controller, plate="plate1", submodule="gui", params=params)

    simulator.ha.assert_service_called("mqtt/publish", data_contains={"topic": "hasp/plate1/config/gui", "payload": payload})


async def test_background_tasks_are_released(page: PageController, plate: FakePlate):
    async def callback(topic, payload):
        pass

    task = await util_openhasp.listen_event(controller=page.controller, client=page.client, path="x", callback=callback)
    assert task in util_openhasp._background_tasks

    task.cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert task not in util_openhasp._background_tasks
