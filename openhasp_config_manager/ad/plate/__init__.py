import copy
from asyncio import Task
from enum import StrEnum
from typing import Dict, Callable, Set, Optional, Awaitable, Any, TYPE_CHECKING

from appdaemon import ADAPI

from openhasp_config_manager.ad import util_openhasp
from openhasp_config_manager.ad.plate.deployment import DeploymentController
from openhasp_config_manager.ad.plate.screen import ScreenController
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater, PageController
else:
    StateUpdater = Any


class ScreenState:
    """
    Screen state for OpenHASP plates.
    """

    def __init__(
        self,
        on: bool = True,
        brightness: int = 255
    ):
        self.on = on
        self.brightness = brightness


class PlateConfig:
    """
    Configuration for an OpenHASP plate.
    """

    def __init__(
        self,
        screen_brightness_default: ScreenState = ScreenState(True, 255),
        screen_brightness_short_idle: ScreenState = ScreenState(True, 20),
        screen_brightness_long_idle: ScreenState = ScreenState(False, 255),
    ):
        self.screen_brightness_default = screen_brightness_default
        self.screen_brightness_short_idle = screen_brightness_short_idle
        self.screen_brightness_long_idle = screen_brightness_long_idle


class PlateBehavior(StrEnum):
    """
    Behaviors for OpenHASP plates.
    """
    # Keeps the screen always on
    ALWAYS_ON_DISPLAY = "always_on"


class PlateController:
    """
    Controller for an OpenHASP plate.
    """

    def __init__(self, app: ADAPI, state_updater: StateUpdater, name: str, config: PlateConfig = PlateConfig()):
        self.app = app
        self.state_updater = state_updater
        self._name = name
        self._config = config

        self.pages: Dict[int, PageController] = {}

        self.deployment_controller = DeploymentController(
            app=self.app,
            name=self._name,
        )

        self.screen_controller = ScreenController(
            app=self.app,
            client=self.client,
            deployment_controller=self.deployment_controller,
        )

        # keeps track of active PlateBehaviors by mapping to the page ids that
        # currently have them added/active
        self.current_behavior_requests: Dict[PlateBehavior, Set[int]] = {}

    async def request_behavior(self, page: PageController, behavior: PlateBehavior):
        """
        Adds a behavior request to the plate
        :param page: the page adding the behavior
        :param behavior: the behavior to add
        """
        if behavior not in self.current_behavior_requests:
            self.current_behavior_requests[behavior] = set()
        if self.has_behavior_request(behavior=behavior, page=page, store=self.current_behavior_requests):
            return
        self.app.log(f"Adding behavior '{behavior}' to plate {self._name}")
        previous_behaviors = copy.deepcopy(self.current_behavior_requests)
        self.current_behavior_requests[behavior].add(page.index)
        await self.update_plate_behavior(previous_behaviors)

    async def drop_behavior_request(self, page: PageController, behavior: PlateBehavior):
        """
        Removes a behavior from the plate
        :param page: the page removing the behavior
        :param behavior: the behavior to remove
        """
        previous_behaviors = copy.deepcopy(self.current_behavior_requests)
        if self.has_behavior_request(behavior=behavior, page=page, store=self.current_behavior_requests):
            self.app.log(f"Removing behavior '{behavior}' from plate {self._name}")
            self.current_behavior_requests[behavior].remove(page.index)
            await self.update_plate_behavior(previous_behaviors)

    def has_behavior_request(
        self,
        behavior: PlateBehavior,
        page: Optional[PageController] = None,
        store: Dict[PlateBehavior, Set[int]] = None
    ) -> bool:
        """
        Checks if the plate has the given behavior active by any page
        :param behavior: the behavior to check
        :param page: (optional) the page to check for, if given only checks if that page has the behavior
        :param store: (optional) the store to check, defaults to active_behaviors
        :return: true if the behavior is active on any page, false otherwise
        """
        if store is None:
            store = self.current_behavior_requests

        pages_with_behavior = store.get(behavior, set())
        if page is not None:
            return page.index in pages_with_behavior
        return len(pages_with_behavior) > 0

    async def update_plate_behavior(self, previous_requests: Dict[PlateBehavior, Set[int]]):
        self.app.log(f"Updating behaviors for plate {self._name}: {list(self.current_behavior_requests.keys())}")
        if self.has_behavior_request(PlateBehavior.ALWAYS_ON_DISPLAY):
            await self.set_gui_config2(idle1=15, idle2=0)
            await self.screen_controller.set_idle(state="short")
        else:
            await self.screen_controller.set_default_auto_brightness_config()

    @property
    def client(self) -> OpenHaspClient:
        return self.deployment_controller.client

    def add_page(self, page: PageController) -> PageController:
        self.app.log(f"Adding page '{page.__class__.__name__}' at index {page.index} to plate {self._name}")
        self.pages[page.index] = page
        return page

    def has_page(self, page: PageController) -> bool:
        return page in self.pages.values()

    def create_page(self, index: int) -> PageController:
        page = PageController(
            app=self.app,
            plate=self,
            state_updater=self.state_updater,
            index=index
        )
        self.pages[index] = page
        return page

    async def init(self):
        await self.screen_controller.init()
        await self.setup_auto_brightness()

        self.app.log(f"Initializing {len(self.pages)} pages for plate {self._name}...")

        for page in self.pages.values():
            self.app.log(f"Initializing page {page.index} for plate {self._name}")
            await page.register_objects()
            self.app.log(f"Initializing objects for page {page.index} for plate {self._name}")
            await page.initialize_objects()

    async def setup_auto_brightness(self):
        if self.screen_controller._screen_brightness_task is not None:
            try:
                self.screen_controller._screen_brightness_task.cancel()
            except Exception as ex:
                pass
            finally:
                self._screen_brightness_task = None

        async def _on_status_event(event_topic: str, event_payload: bytes):
            event_payload = event_payload.decode("utf-8")
            if event_payload == "off":
                self.app.log(f"Activating screen, due to state/idle event: {event_payload}")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_default.on,
                    brightness=self._config.screen_brightness_default.brightness
                )
            elif event_payload == "short":
                self.app.log(f"Device idle for short time")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_short_idle.on,
                    brightness=self._config.screen_brightness_short_idle.brightness
                )
            elif event_payload == "long":
                self.app.log(f"Device idle for long time")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_long_idle.on,
                    brightness=self._config.screen_brightness_long_idle.brightness
                )
            else:
                self.app.log(f"Got unexpected state/idle event: {event_topic} - {event_payload}")

        self._screen_brightness_task = await self.listen_openhasp_event(
            path="state/idle",
            callback=_on_status_event
        )

    async def sync(self):
        await self.state_updater.sync()

    async def reboot(self):
        """
        Reboots the device
        """
        return self.client.reboot()

    async def wakeup(self):
        """
        Wakes up the display
        """
        # TODO: this currently wakes up the display indefinitely, it would be nice to be able
        #  to set a timeout after which the display goes back to sleep / default behavior
        return await self.screen_controller.set_idle(state="off")

    async def command(self, cmd: str, params: str = ""):
        return await self.client.command(
            name=cmd,
            params=params,
        )

    async def change_page(self, index: int):
        return await self.client.set_page(index)

    async def set_gui_config2(
        self,
        idle1: int = None, idle2: int = None,
        rotate: int = None, cursor: int = None, bckl: int = None
    ):
        gui_config = GuiConfig(
            idle1=idle1,
            idle2=idle2,
            rotate=rotate,
            cursor=cursor,
            bckl=bckl,
            bcklinv=None,
            invert=None,
            calibration=None,
        )
        self.client.set_gui_config(gui_config)

    async def set_gui_config(
        self,
        idle1: int = None, idle2: int = None,
        rotate: int = None, cursor: int = None, bckl: int = None
    ):
        parameters = {
            "idle1": idle1,
            "idle2": idle2,
            "rotate": rotate,
            "cursor": cursor,
            "bckl": bckl,
        }
        # ignore keys with None value
        parameters = {k: v for k, v in parameters.items() if v is not None}

        return await self._set_config(
            submodule="gui",
            parameters=parameters
        )

    async def _set_config(self, submodule: str, parameters: Dict):
        self.app.log(f"Setting {submodule} config: {parameters}")
        return await util_openhasp.config(
            controller=self.app,
            plate=self._name,
            submodule=submodule,
            params=parameters,
        )

    async def listen_openhasp_event(self, path: str, callback: Callable[[str, bytes], Awaitable[Any]]) -> Task:
        """
        Listens to events for the given object on the plate of this controller and calls the callback with it
        :param path: sub-path for this plate to listen for
        :param callback: called when an event is received
        """
        return await util_openhasp.listen_event(
            controller=self.app,
            client=self.client,
            path=path,
            callback=callback,
        )
