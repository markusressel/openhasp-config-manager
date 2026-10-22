import json
import logging

import pytest

from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import PlateConfig, PlateController, ScreenState
from tests.haad.conftest import PlateUnderTest, page_at
from tests.haad.fakes import FakePlate, Http


@pytest.fixture
def plate_controller(page: PageController) -> PlateController:
    return page.plate


def _gui_config_publishes(simulator) -> list:
    return [call["data"] for call in simulator.ha.called_services if call["action"] == "mqtt/publish"]


async def test_keep_awake_applies_the_always_on_config_or_the_gui_defaults(simulator, plate_controller, plate: FakePlate):
    plate.clear()

    await plate_controller.set_keep_awake(True)
    assert [m if isinstance(m, Http) else f"{m.topic.rsplit('/', 1)[1]} {m.payload}" for m in plate.traffic] == [
        Http("POST", "config", {"idle1": 15, "idle2": 0, "save": "gui"}),
        "idle short",
    ]
    assert _gui_config_publishes(simulator) == []
    plate.clear()

    # back to the device's gui defaults, over MQTT (through Home Assistant, to the plate's *controller* name) and HTTP
    await plate_controller.set_keep_awake(False)
    assert [m if isinstance(m, Http) else f"{m.topic.rsplit('/', 1)[1]} {m.payload}" for m in plate.traffic] == [
        Http("POST", "config", {"idle1": 60, "idle2": 120, "save": "gui"}),
        "idle off",
    ]
    assert _gui_config_publishes(simulator) == [
        {"topic": "hasp/test_device/config/gui", "payload": '{"idle1": 60, "idle2": 120}'}
    ]


async def test_pages(plate_controller, page: PageController):
    created = plate_controller.create_page(index=5)

    assert type(created) is PageController
    assert created.index == 5 and created.plate is plate_controller
    assert plate_controller.pages == {1: page, 5: created}
    assert plate_controller.has_page(created)
    assert not plate_controller.has_page(page_at(6)(page.controller))
    assert plate_controller.add_page(page_at(1)(page.controller)) is plate_controller.pages[1]


async def test_auto_brightness_follows_idle_state(plate_controller, plate: FakePlate, caplog):
    await plate.send("state/idle", "short")
    await plate.send("state/idle", "long")
    await plate.send("state/idle", "off")
    with caplog.at_level(logging.WARNING):
        await plate.send("state/idle", "unexpected")

    assert plate.commands == [
        'backlight {"state": true, "brightness": 20}',
        'backlight {"state": false, "brightness": 255}',
        'backlight {"state": true, "brightness": 255}',
    ]
    assert "Got unexpected state/idle event: hasp/mqtt_name/state/idle - unexpected" in caplog.text


async def test_auto_brightness_uses_plate_config(start_plate, plate: FakePlate):
    class CustomPlate(PlateUnderTest):
        @property
        def plate_config(self) -> PlateConfig:
            return PlateConfig(
                screen_brightness_default=ScreenState(True, 200),
                screen_brightness_short_idle=ScreenState(True, 10),
                screen_brightness_long_idle=ScreenState(True, 1),
            )

    await start_plate(CustomPlate)
    plate.clear()

    await plate.send("state/idle", "short")
    await plate.send("state/idle", "long")
    await plate.send("state/idle", "off")

    assert plate.commands == [
        'backlight {"state": true, "brightness": 10}',
        'backlight {"state": true, "brightness": 1}',
        'backlight {"state": true, "brightness": 200}',
    ]


async def test_setup_auto_brightness_again_adds_a_second_listener(plate_controller, plate: FakePlate):
    """The check for a previous listener looks at the screen controller, but the listener is stored on the plate controller."""
    await plate_controller.setup_auto_brightness()

    await plate.send("state/idle", "short")

    assert plate.commands == ['backlight {"state": true, "brightness": 20}'] * 2


@pytest.mark.parametrize("cancel_raises", [False, True])
async def test_setup_auto_brightness_cancels_screen_controller_task(plate_controller, cancel_raises):
    """Unreachable today: nothing sets screen_controller._screen_brightness_task."""
    cancelled = []

    class _Task:
        def cancel(self):
            cancelled.append(True)
            if cancel_raises:
                raise RuntimeError("cancel failed")

    plate_controller.screen_controller._screen_brightness_task = _Task()

    await plate_controller.setup_auto_brightness()

    assert cancelled == [True]
    # the reset goes to the plate controller's attribute, which then gets the new listener
    assert plate_controller.screen_controller._screen_brightness_task is not None
    assert plate_controller._screen_brightness_task is not None


async def test_sync_clears_caches_and_syncs_all_objects(simulator, page: PageController, plate_controller, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.p", "10")
    bar = await page.add_bar(obj_id=28, entity="sensor.p")
    await bar.init()
    plate.clear()

    await plate_controller.sync()

    assert plate.commands == ["p1b28.enabled=True", "p1b28.val=10"]


async def test_plate_commands(plate_controller, plate: FakePlate):
    await plate_controller.wakeup()
    await plate_controller.command("clearpage", "all")
    await plate_controller.command("restart")
    await plate_controller.change_page(index=3)
    await plate_controller.reboot()

    assert plate.commands == ["idle off", "clearpage all", "restart ", "page 3"]
    assert plate.http == [Http("GET", "reboot")]


async def test_set_gui_config(simulator, plate_controller, plate: FakePlate):
    await plate_controller.set_gui_config(idle1=1, idle2=2, rotate=3, cursor=4, bckl=5)
    await plate_controller.set_gui_config(idle1=7)
    await plate_controller.set_gui_config2(idle1=1, idle2=2, rotate=3, cursor=4, bckl=5)
    await plate_controller.set_gui_config2(bckl=9)

    assert [json.loads(data["payload"]) for data in _gui_config_publishes(simulator)] == [
        {"idle1": 1, "idle2": 2, "rotate": 3, "cursor": 4, "bckl": 5},
        {"idle1": 7},
    ]
    assert plate.http == [
        Http("POST", "config", {"idle1": 1, "idle2": 2, "rotate": 3, "cursor": 4, "bckl": 5, "save": "gui"}),
        Http("POST", "config", {"bckl": 9, "save": "gui"}),
    ]


async def test_listen_openhasp_event(plate_controller, plate: FakePlate):
    events = []

    async def callback(topic, payload):
        events.append((topic, payload))

    await plate_controller.listen_openhasp_event(path="custom", callback=callback)
    await plate.send("custom", "x")

    assert events == [("hasp/mqtt_name/custom", b"x")]
