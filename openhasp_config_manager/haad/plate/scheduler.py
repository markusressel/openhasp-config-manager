"""
Decides which page a plate shows and whether its screen stays on: pages declare *claims* on the plate, and the plate
arbitrates between the active ones by priority (like Android's audio focus or alarm priorities, with a rotation like a
digital signage playlist that a touch interrupts).

- A claim is active while its condition holds (`Claim.active`, re-evaluated whenever its trigger fires).
- The plate stays on while any active claim has `keep_awake`.
- Only the claims of the highest active priority count: when one of them becomes active, its page is shown. With
  several of them active, the plate rotates through their pages, `FocusConfig.dwell` each. Claims of a lower priority
  show their page once the higher ones are gone.
- A touch pins the page the user is on: nothing switches the page, nor rotates, until `FocusConfig.pin` has passed since
  the last touch. Only a claim with `Priority.CRITICAL` breaks through a pin.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Awaitable, Callable, List, Optional

from haad.controller import HaadController
from haad.triggers import TimeTrigger
from haad.triggers.resolver import TriggerInput

if TYPE_CHECKING:
    from openhasp_config_manager.haad.page import PageController
    from openhasp_config_manager.haad.plate import PlateController

# the events of an object that are a touch (not "changed": that follows commands, too)
TOUCH_EVENTS = {"down", "up", "short", "long", "hold", "release", "lost"}
_OBJECT_EVENT_TOPIC = re.compile(r"/state/p\d+b\d+$")
_PAGE_EVENT_TOPIC = re.compile(r"/state/page$")
_IDLE_EVENT_TOPIC = re.compile(r"/state/idle$")


class Priority(IntEnum):
    """How much a claim matters. Only the claims of the highest active priority are shown."""

    AMBIENT = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(frozen=True)
class FocusConfig:
    """When a plate switches pages."""

    # how long the pages of equal claims are shown while rotating
    dwell: timedelta = timedelta(seconds=15)
    # how long after the last touch the page stays as the user left it
    pin: timedelta = timedelta(seconds=60)
    # the page to go to when the last claim ends; None: stay on the page
    home_page: Optional[int] = None


@dataclass(eq=False)
class Claim:
    """A page's demand on the plate while its condition holds, see `PageController.claim()`."""

    page: "PageController"
    # whether the claim is active, evaluated when `trigger` fires
    active: Callable[[], Awaitable[bool]]
    priority: Priority = Priority.NORMAL
    # keeps the screen on (no idle dimming) while active
    keep_awake: bool = False
    # wakes the screen when the claim shows its page
    wake: bool = False
    # when it became active (a counter, newest is highest); None while inactive
    activated: Optional[int] = field(default=None, init=False)


class Mode(StrEnum):
    # shows what the claims say; nothing to rotate
    IDLE = "idle"
    # several claims of the top priority: switches the page every `dwell`
    ROTATING = "rotating"
    # the user touched the plate: nothing switches the page until `pin` passed
    PINNED = "pinned"


class PageScheduler:
    """
    The page and screen arbitration of a plate. All events (claim changes, touches, timers) are handled one after
    the other, so the mode and its single timer never interleave.
    """

    def __init__(self, controller: HaadController, plate: "PlateController", config: FocusConfig):
        self._controller = controller
        self._plate = plate
        self._config = config

        self.mode = Mode.IDLE
        self._claims: List[Claim] = []
        self._counter = 0
        self._started = False
        self._lock = asyncio.Lock()
        # the pin expiry or the next rotation, depending on the mode; a firing timer is stale if its sequence is not current
        self._timer = None
        self._timer_sequence = 0
        self._current_page: Optional[int] = None
        self._expected_page: Optional[int] = None
        # whether the plate was told to stay on; a plate that restarted is back to its defaults
        self._awake = False
        self._listeners: List[asyncio.Task] = []

    @property
    def active_claims(self) -> List[Claim]:
        return [c for c in self._claims if c.activated is not None]

    async def register(
        self,
        page: "PageController",
        active: Callable[[], Awaitable[bool]],
        trigger: TriggerInput,
        priority: Priority = Priority.NORMAL,
        keep_awake: bool = False,
        wake: bool = False,
    ) -> Claim:
        """Adds a claim, evaluated now and whenever `trigger` fires."""
        claim = Claim(page=page, active=active, priority=priority, keep_awake=keep_awake, wake=wake)
        self._claims.append(claim)

        async def _evaluate():
            await self._evaluate(claim)

        await self._controller.react_to(trigger=trigger, action=_evaluate, immediately=True)
        return claim

    async def start(self):
        """
        Starts reacting to touches and applies the claims that became active before (the pages are pushed by now).
        """
        self._started = True
        self._listeners.append(await self._plate.listen_openhasp_event(path="state/+", callback=self._on_event))
        async with self._lock:
            await self._resync()

    async def stop(self):
        self._started = False
        for listener in self._listeners:
            listener.cancel()
        self._listeners.clear()
        await self._clear_timer()

    async def resync(self):
        """Applies the claims again, e.g. after the plate rebooted and forgot its screen config and page."""
        async with self._lock:
            self._awake = False
            self._current_page = None
            await self._pin_cleared()
            await self._resync()

    # -- events

    async def _evaluate(self, claim: Claim):
        is_active = await claim.active()
        async with self._lock:
            if is_active == (claim.activated is not None):
                return
            if is_active:
                self._counter += 1
                claim.activated = self._counter
            else:
                claim.activated = None
            self._controller.logger.info(
                f"Claim of page {claim.page.index} ({claim.priority.name}) is {'active' if is_active else 'inactive'}"
            )
            if self._started:
                await self._on_claim_changed(claim)

    async def _on_claim_changed(self, claim: Claim):
        await self._apply_awake()
        top = self._top_claims()
        if claim.activated is not None:
            takes_the_page = claim in top and (self.mode is not Mode.PINNED or claim.priority is Priority.CRITICAL)
            if takes_the_page:
                if claim.wake:
                    await self._plate.wakeup()
                await self._pin_cleared()
                await self._show(claim.page.index)
        elif self.mode is not Mode.PINNED:
            await self._show_top()
        await self._update_rotation()

    async def _on_event(self, topic: str, payload: bytes):
        if _PAGE_EVENT_TOPIC.search(topic):
            page = int(payload.decode("utf-8"))
            expected, self._expected_page = self._expected_page, None
            self._current_page = page
            if page == expected:
                return
        elif _IDLE_EVENT_TOPIC.search(topic):
            # a touch wakes a dimmed screen ("off"); this includes taps on the empty background, but also haad's own wakeups
            if payload.decode("utf-8") != "off":
                return
        elif _OBJECT_EVENT_TOPIC.search(topic):
            event = json.loads(payload).get("event")
            if event not in TOUCH_EVENTS:
                return
        else:
            return
        async with self._lock:
            await self._pin()

    async def _on_timer(self, sequence: int):
        async with self._lock:
            # an event that came in while this waited for the lock replaced the timer
            if sequence != self._timer_sequence:
                return
            # spent: nothing to cancel
            self._timer = None
            if self.mode is Mode.PINNED:
                self.mode = Mode.IDLE
                top_pages = self._top_pages()
                if top_pages and self._current_page not in top_pages:
                    await self._show_top()
                await self._update_rotation()
            else:
                # rotating: every claim change re-arms the timer, so there are at least two pages, one of them shown
                pages = self._top_pages()
                await self._show(pages[(pages.index(self._current_page) + 1) % len(pages)])
                await self._update_rotation()

    # -- decisions

    def _top_claims(self) -> List[Claim]:
        active = self.active_claims
        if not active:
            return []
        highest = max(c.priority for c in active)
        return sorted((c for c in active if c.priority == highest), key=lambda c: c.activated, reverse=True)

    def _top_pages(self) -> List[int]:
        """The pages of the top claims, newest first, without duplicates."""
        return list(dict.fromkeys(c.page.index for c in self._top_claims()))

    async def _resync(self):
        await self._apply_awake()
        await self._show_top()
        await self._update_rotation()

    async def _show_top(self):
        """Shows the page of the newest top claim, unless a page of the top claims is shown already."""
        pages = self._top_pages()
        if pages:
            if self._current_page not in pages:
                await self._show(pages[0])
        elif self._config.home_page is not None:
            await self._show(self._config.home_page)

    async def _show(self, index: int):
        if index != self._current_page:
            self._expected_page = index
            self._current_page = index
            await self._plate.change_page(index)

    async def _apply_awake(self):
        awake = any(c.keep_awake for c in self.active_claims)
        if awake != self._awake:
            self._awake = awake
            await self._plate.set_keep_awake(awake)

    # -- mode and timer

    async def _pin(self):
        await self._arm(Mode.PINNED, self._config.pin)

    async def _pin_cleared(self):
        if self.mode is Mode.PINNED:
            await self._arm(Mode.IDLE, None)

    async def _update_rotation(self):
        if self.mode is Mode.PINNED:
            return
        if len(self._top_pages()) > 1:
            await self._arm(Mode.ROTATING, self._config.dwell)
        else:
            await self._arm(Mode.IDLE, None)

    async def _arm(self, mode: Mode, delay: Optional[timedelta]):
        """Switches to `mode` with its timer: the pin expiry or the next rotation (None: no timer)."""
        await self._clear_timer()
        self.mode = mode
        if delay is not None:
            sequence = self._timer_sequence

            async def _fire():
                await self._on_timer(sequence)

            self._timer = await self._controller.schedule(trigger=TimeTrigger.after(delay), action=_fire)

    async def _clear_timer(self):
        # replaced before awaiting the cancel, and a timer that fires meanwhile is stale by its sequence
        handle, self._timer = self._timer, None
        self._timer_sequence += 1
        if handle is not None:
            await self._controller.cancel_schedule(handle)
