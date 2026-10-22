"""Page claims: which page a plate shows, when it stays on, rotation, and touches (PageScheduler)."""
from datetime import timedelta
from typing import Awaitable, Callable

import pytest

from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import PlateConfig
from openhasp_config_manager.haad.plate.scheduler import FocusConfig, Mode, Priority
from tests.haad.conftest import PLACEHOLDER_ID, PlateUnderTest, page_at
from tests.haad.fakes import FakePlate, Http

DWELL = timedelta(seconds=15)
PIN = timedelta(seconds=60)
ALWAYS_ON = Http("POST", "config", {"idle1": 15, "idle2": 0, "save": "gui"})
DEFAULTS = Http("POST", "config", {"idle1": 60, "idle2": 120, "save": "gui"})


def claiming(entity: str, **claim) -> Callable:
    """A page whose claim is active while `entity` is "on"."""

    class ClaimingPage(PageController):
        async def register_objects(self):
            await self.add_label(obj_id=PLACEHOLDER_ID)

            async def _on() -> bool:
                return await self.controller.ha.get_state(entity) == "on"

            self.claimed = await self.claim(active=_on, trigger=entity, **claim)

    return ClaimingPage


class FocusPlate(PlateUnderTest):
    focus = FocusConfig(dwell=DWELL, pin=PIN)

    @property
    def plate_config(self) -> PlateConfig:
        return PlateConfig(focus=self.focus)


class HomePlate(FocusPlate):
    focus = FocusConfig(dwell=DWELL, pin=PIN, home_page=1)


@pytest.fixture
def pages(simulator, start_plate, plate: FakePlate):
    async def _start(*specs, cls=FocusPlate, states=()):
        for entity, state in states:
            await simulator.ha.trigger_state_change(entity, state)
        controller = await start_plate(cls, pages=[page_at(i, claiming(e, **c)) for i, (e, c) in enumerate(specs, start=1)])
        plate.clear()
        return controller.plate_controller

    return _start


def _pages(plate: FakePlate) -> list:
    """The pages the plate was told to show since the last clear, and clears."""
    result = [c for c in plate.commands if c.startswith("page ")]
    plate.clear()
    return result


async def _set(simulator, plate: FakePlate, entity: str, state: str):
    await simulator.ha.trigger_state_change(entity, state)
    await plate.settle()


async def _touch(plate: FakePlate, page: int = 1):
    await plate.send(f"state/p{page}b{PLACEHOLDER_ID}", {"event": "up"})


async def _wait(simulator, plate: FakePlate, delta: timedelta):
    await simulator.advance(delta)
    await plate.settle()


async def test_an_active_claim_shows_its_page_and_keeps_the_screen_on(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {"keep_awake": True}), ("switch.b", {}), states=[("switch.a", "off")])

    await _set(simulator, plate, "switch.b", "on")
    assert plate.commands == ["page 2"]
    plate.clear()

    await _set(simulator, plate, "switch.a", "on")
    assert plate.commands == ["idle short", "page 1"]
    assert plate.http == [ALWAYS_ON]
    plate.clear()

    await _set(simulator, plate, "switch.a", "off")
    assert plate.http == [DEFAULTS]


async def test_claims_that_are_active_at_the_start_are_applied_after_the_pages_are_pushed(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change("switch.a", "on")

    await start_plate(FocusPlate, pages=[page_at(1), page_at(2, claiming("switch.a", keep_awake=True))])

    assert "page 2" in plate.commands
    assert "idle short" in plate.commands
    assert ALWAYS_ON in plate.http


async def test_the_last_claim_ends_stays_on_the_page_or_goes_home(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {}), ("switch.b", {}), cls=HomePlate)
    await _set(simulator, plate, "switch.b", "on")
    assert _pages(plate) == ["page 2"]

    await _set(simulator, plate, "switch.b", "off")
    assert _pages(plate) == ["page 1"]


async def test_the_page_stays_when_there_is_no_home_page(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {}), ("switch.b", {}))
    await _set(simulator, plate, "switch.b", "on")
    plate.clear()

    await _set(simulator, plate, "switch.b", "off")

    assert _pages(plate) == []


async def test_a_lower_priority_claim_does_not_take_the_page_until_the_higher_one_ends(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {"priority": Priority.HIGH}), ("switch.b", {"priority": Priority.NORMAL}))
    await _set(simulator, plate, "switch.a", "on")
    assert _pages(plate) == ["page 1"]

    await _set(simulator, plate, "switch.b", "on")
    assert _pages(plate) == []

    await _set(simulator, plate, "switch.a", "off")
    assert _pages(plate) == ["page 2"]

    # a higher one takes the page
    await _set(simulator, plate, "switch.a", "on")
    assert _pages(plate) == ["page 1"]


async def test_claims_of_the_same_priority_rotate_and_the_newest_is_shown_first(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {}), ("switch.c", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    assert _pages(plate) == ["page 1"]
    assert scheduler.mode is Mode.IDLE

    await _set(simulator, plate, "switch.b", "on")
    assert _pages(plate) == ["page 2"]
    assert scheduler.mode is Mode.ROTATING

    await _wait(simulator, plate, DWELL)
    await _wait(simulator, plate, DWELL)
    await _wait(simulator, plate, DWELL)
    assert _pages(plate) == ["page 1", "page 2", "page 1"]

    # a third: shown right away, then the rotation continues from there
    await _set(simulator, plate, "switch.c", "on")
    await _wait(simulator, plate, DWELL)
    assert _pages(plate) == ["page 3", "page 2"]

    # only one left: no more rotation
    await _set(simulator, plate, "switch.a", "off")
    await _set(simulator, plate, "switch.b", "off")
    plate.clear()
    await _wait(simulator, plate, DWELL * 3)
    assert _pages(plate) == []
    assert scheduler.mode is Mode.IDLE


async def test_a_touch_pins_the_page_until_the_pin_timeout_since_the_last_touch(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    await _set(simulator, plate, "switch.b", "on")
    plate.clear()

    await _touch(plate)
    assert scheduler.mode is Mode.PINNED
    await _wait(simulator, plate, timedelta(seconds=40))
    await _touch(plate)
    await _wait(simulator, plate, timedelta(seconds=40))
    # no rotation while pinned
    assert _pages(plate) == []

    # a new claim does not take the page either
    await _set(simulator, plate, "switch.b", "off")
    await _set(simulator, plate, "switch.b", "on")
    assert _pages(plate) == []

    # unpinned: the rotation goes on
    await _wait(simulator, plate, timedelta(seconds=20))
    assert scheduler.mode is Mode.ROTATING
    await _wait(simulator, plate, DWELL)
    assert len(_pages(plate)) == 1


async def test_when_the_pin_ends_the_newest_claim_page_is_shown_if_the_user_is_elsewhere(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {}), ("switch.b", {}))
    await _set(simulator, plate, "switch.a", "on")
    plate.clear()

    # the user swipes to page 2
    await plate.send("state/page", "2")
    await _wait(simulator, plate, PIN)
    assert _pages(plate) == ["page 1"]


async def test_a_claim_that_ends_while_pinned_waits_for_the_pin_to_end(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {}), ("switch.b", {}))
    await _set(simulator, plate, "switch.a", "on")
    await _set(simulator, plate, "switch.b", "on")
    await _touch(plate)
    plate.clear()

    await _set(simulator, plate, "switch.b", "off")
    assert _pages(plate) == []

    await _wait(simulator, plate, PIN)
    assert _pages(plate) == ["page 1"]


async def test_a_critical_claim_breaks_through_a_pin_and_wakes_the_screen(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {"priority": Priority.CRITICAL, "wake": True}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    await _touch(plate)
    plate.clear()

    await _set(simulator, plate, "switch.b", "on")

    assert plate.commands == ["idle off", "page 2"]
    assert scheduler.mode is Mode.IDLE


async def test_a_critical_claim_without_wake_does_not_wake_the_screen(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {"priority": Priority.CRITICAL}))

    await _set(simulator, plate, "switch.a", "on")

    assert plate.commands == ["page 1"]


async def test_own_page_changes_are_not_touches_but_swipes_are(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    # the plate reports the page it was told to show
    await plate.send("state/page", "1")
    assert scheduler.mode is Mode.IDLE

    await plate.send("state/page", "2")
    assert scheduler.mode is Mode.PINNED


async def test_only_touches_pin(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}),)).scheduler

    await plate.send(f"state/p1b{PLACEHOLDER_ID}", {"event": "changed", "val": 1})
    await plate.send("state/idle", "short")
    await plate.send("state/idle", "long")
    await plate.send("state/sensors", {"tele": 1})
    assert scheduler.mode is Mode.IDLE

    await plate.send(f"state/p1b{PLACEHOLDER_ID}", {"event": "down"})
    assert scheduler.mode is Mode.PINNED


async def test_a_touch_that_wakes_the_screen_pins(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}),)).scheduler

    await plate.send("state/idle", "off")

    assert scheduler.mode is Mode.PINNED


async def test_lwt_online_applies_the_claims_again(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {"keep_awake": True}), ("switch.b", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    await _touch(plate)
    plate.clear()

    await plate.send("LWT", "online")
    await _wait(simulator, plate, timedelta(seconds=1))

    # the plate forgot its screen config and page, and the pin
    assert "page 1" in plate.commands
    assert ALWAYS_ON in plate.http
    assert scheduler.mode is Mode.IDLE


async def test_stop_cancels_the_timer_and_the_listener(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    await _set(simulator, plate, "switch.b", "on")
    plate.clear()

    await scheduler.stop()
    await _wait(simulator, plate, DWELL * 2)
    await _touch(plate)

    assert _pages(plate) == []
    assert scheduler.mode is Mode.ROTATING


async def test_a_stale_timer_is_ignored(simulator, plate: FakePlate, pages):
    scheduler = (await pages(("switch.a", {}), ("switch.b", {}))).scheduler
    await _set(simulator, plate, "switch.a", "on")
    await _set(simulator, plate, "switch.b", "on")
    plate.clear()

    await scheduler._on_timer(-1)

    assert _pages(plate) == []


async def test_an_unchanged_claim_does_nothing(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {"keep_awake": True}))
    await _set(simulator, plate, "switch.a", "on")
    plate.clear()

    await simulator.ha.trigger_state_change("switch.a", "on", {"brightness": 5})
    await plate.settle()

    assert plate.traffic == []


async def test_a_claim_on_the_page_that_is_shown_sends_no_page_change(simulator, plate: FakePlate, pages):
    await pages(("switch.a", {}))
    await _set(simulator, plate, "switch.a", "on")
    await _set(simulator, plate, "switch.a", "off")
    plate.clear()

    await _set(simulator, plate, "switch.a", "on")

    assert _pages(plate) == []
