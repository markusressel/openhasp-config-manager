import logging
from datetime import timedelta

import pytest

from openhasp_config_manager.haad.controller import OpenHaspController
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import PlateConfig
from tests.haad.conftest import EmptyPage, PlateUnderTest, page_at
from tests.haad.fakes import FakePlate, Http, Mqtt


class LabelPage(PageController):
    async def register_objects(self):
        await self.add_label(obj_id=10, entity="sensor.time")


async def test_startup_traffic(simulator, plate: FakePlate, load_plate):
    """After 1 s: online check, gui defaults, objects; 1 s later: the first sync."""
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    controller = load_plate(pages=[page_at(1, LabelPage)])

    await simulator.start(controller)
    await plate.settle()
    assert plate.traffic == []
    assert plate.subscribed  # the LWT listener

    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        Http("POST", "config", {"idle1": 60, "idle2": 120, "rotate": 1, "cursor": 0, "bckl": 32, "save": "gui"}),
        Mqtt("hasp/mqtt_name/command", "p1b10.text=12:00"),
        Mqtt("hasp/mqtt_name/command", "p1b10.text=12:00"),
    ]

    plate.clear()
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    assert plate.commands == ["p1b10.text=12:00"]

    await controller.terminate()


async def test_setup_waits_until_the_plate_is_online(simulator, plate: FakePlate, load_plate, caplog):
    plate.online = False
    controller = load_plate(pages=[page_at(1, LabelPage)])
    await simulator.start(controller)

    with caplog.at_level(logging.INFO):
        await simulator.advance(timedelta(seconds=1))
    assert "Plate 'test_device' is not online yet, retrying in 10..." in caplog.text
    assert controller.plate_controller.pages == {}

    await simulator.advance(timedelta(seconds=9))
    assert controller.plate_controller.pages == {}

    plate.online = True
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    assert list(controller.plate_controller.pages) == [1]
    # sensor.time does not exist: None
    assert plate.commands == ["p1b10.text=None", "p1b10.text=None"]

    await simulator.advance(timedelta(seconds=1))
    await controller.terminate()


async def test_setup_errors_are_logged_without_retry(simulator, plate: FakePlate, load_plate, caplog):
    """OpenHaspController.setup_plate() must be overridden; errors are logged and the setup is not retried."""
    controller = load_plate(OpenHaspController)
    await simulator.start(controller)

    await simulator.advance(timedelta(seconds=1))
    assert "Failed to setup plate 'test_device', retrying in 10: <class 'NotImplementedError'>" in caplog.text

    plate.clear()
    await simulator.advance(timedelta(seconds=30))
    assert plate.traffic == []

    # the first sync was never scheduled
    with pytest.raises(AttributeError, match="_plate_sync_timer_task"):
        await controller.terminate()


async def test_lwt_online_syncs_after_one_second(simulator, start_plate, plate: FakePlate, caplog):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    await start_plate(pages=[page_at(1, LabelPage)])
    plate.clear()

    with caplog.at_level(logging.INFO):
        await plate.send("LWT", "offline")
        await simulator.advance(timedelta(seconds=5))
    assert "Received LWT event for plate test_device: offline" in caplog.text
    assert plate.traffic == []

    await plate.send("LWT", "online")
    assert plate.traffic == []
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    assert plate.commands == ["p1b10.text=12:00"]


async def test_online_state_listener_is_set_up_once(simulator, start_plate, plate: FakePlate):
    controller = await start_plate(pages=[page_at(1, LabelPage)])
    task = controller._lwt_task

    await controller.setup_online_state_listener()

    assert controller._lwt_task is task


async def test_terminate(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.time", "12:00")
    controller = await start_plate(pages=[page_at(1, LabelPage)])
    await plate.send("LWT", "online")

    await controller.terminate()
    await plate.settle()

    assert controller._lwt_task is None
    assert controller.state_updater._registered_objects == {}
    plate.clear()
    # the scheduled sync was cancelled, and the LWT listener is gone
    await simulator.advance(timedelta(seconds=5))
    await plate.send("LWT", "online")
    await simulator.advance(timedelta(seconds=5))
    assert plate.traffic == []

    # terminating twice is fine (the LWT listener is only cancelled once)
    await controller.terminate()


async def test_terminate_before_setup(simulator, load_plate, plate: FakePlate):
    """`_plate_sync_timer_task` only exists after the setup."""
    controller = load_plate(pages=[page_at(1, EmptyPage)])
    await simulator.start(controller)

    with pytest.raises(AttributeError, match="_plate_sync_timer_task"):
        await controller.terminate()


async def test_controller_api(start_plate):
    controller = await start_plate(pages=[page_at(1)])
    page = page_at(2)(controller)

    assert controller.add_page(page) is page
    assert controller.plate_controller.pages[2] is page
    assert type(OpenHaspController.plate_config.fget(controller)) is PlateConfig
    assert controller._config_dir == controller.context.config.config_dir
    assert controller._output_dir == controller.context.config.output_dir
    assert isinstance(controller, PlateUnderTest)


async def test_teardown_without_scheduled_tasks(start_plate):
    """Unreachable today: both handles are always set when teardown_plate_setup() runs after a setup."""
    controller = await start_plate(pages=[page_at(1)])
    controller._plate_setup_scheduled_task = None
    controller._plate_sync_timer_task = None

    await controller.teardown_plate_setup()


class NoObjectsPage(PageController):
    pass


async def test_page_without_objects_fails_the_setup(simulator, plate: FakePlate, load_plate, caplog):
    """register_objects() does nothing by default, so a page that forgot to declare its objects fails here."""
    controller = load_plate(pages=[page_at(1, NoObjectsPage)])
    await simulator.start(controller)

    await simulator.advance(timedelta(seconds=1))

    assert "Page 1 (NoObjectsPage) of plate test_device declares no objects" in caplog.text
