from asyncio import Task
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Callable, Optional, Awaitable, Any, List

from haad.controller import HaadController
from openhasp_config_manager.haad import util_openhasp
from openhasp_config_manager.haad.layout.dump import write_dump
from openhasp_config_manager.haad.layout.render import batch_lines, render_page
from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.page.state_updater import StateUpdater
from openhasp_config_manager.haad.plate import device_factory
from openhasp_config_manager.haad.plate.deployment import DeploymentController
from openhasp_config_manager.haad.plate.scheduler import FocusConfig, PageScheduler
from openhasp_config_manager.haad.plate.screen import ScreenController
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


class ScreenState:
    """
    Screen state for OpenHASP plates.
    """

    def __init__(
        self,
        on: bool = True,
        brightness: int = 255,
    ):
        self.on = on
        self.brightness = brightness


@dataclass(frozen=True)
class Screen:
    """The size of a plate's screen in pixels, as the pages see it (i.e. after rotation)."""
    width: int
    height: int


@dataclass(frozen=True)
class GuiDefaults:
    """The plate's idle timeouts, restored when no page claims the screen to stay on."""
    idle1: int  # seconds until "short" idle
    idle2: int  # seconds until "long" idle


class PlateConfig:
    """
    Configuration for an OpenHASP plate.
    """

    def __init__(
        self,
        screen_brightness_default: ScreenState = ScreenState(True, 255),
        screen_brightness_short_idle: ScreenState = ScreenState(True, 20),
        screen_brightness_long_idle: ScreenState = ScreenState(False, 255),
        screen: Optional[Screen] = None,
        theme: Theme = Theme(),
        gui: Optional[GuiDefaults] = None,
        wrap_navigation: bool = True,
        focus: FocusConfig = FocusConfig(),
    ):
        """
        :param screen: the screen size for code-defined layouts; default: from the device's config (config_dir)
        :param theme: default properties of code-defined objects. Fonts and images it references must be on the plate's flash.
        :param gui: the idle timeouts; default: from the device's config (config_dir)
        :param wrap_navigation: when the plate has code-defined pages, it sets `prev` of the first page and `next` of the
            last page, so swiping cycles through the pages
        :param focus: when the plate switches pages by itself, see PageScheduler
        """
        self.screen_brightness_default = screen_brightness_default
        self.screen_brightness_short_idle = screen_brightness_short_idle
        self.screen_brightness_long_idle = screen_brightness_long_idle
        self.screen = screen
        self.theme = theme
        self.gui = gui
        self.wrap_navigation = wrap_navigation
        self.focus = focus


class PlateController:
    """
    Controller for an OpenHASP plate.
    """

    def __init__(
        self,
        controller: HaadController,
        state_updater: StateUpdater,
        name: str,
        config: PlateConfig = PlateConfig(),
        config_dir: Optional[Path] = Path("/conf/openhasp-configs"),
        output_dir: Path = Path("/conf/openhasp-configs.output"),
        device: Optional[Device] = None,
        layout_dump_dir: Optional[Path] = None,
    ):
        """
        :param config_dir: the openhasp-configs directory the plate's device is read from; None for a plate without one
        :param output_dir: the output directory of the deployment
        :param device: the plate's device, when there is no config_dir (see device_factory.build_device())
        :param layout_dump_dir: where the rendered owned pages are written to (see layout/dump.py); None: nowhere
        """
        self._layout_dump_dir = layout_dump_dir
        self.controller = controller
        self.state_updater = state_updater
        self._name = name
        self._config = config

        self.pages: Dict[int, PageController] = {}
        # the rendered JSONL objects of the owned pages, by page index
        self.rendered: Dict[int, List[Dict[str, Any]]] = {}

        if config_dir is not None:
            self.deployment_controller: Optional[DeploymentController] = DeploymentController(
                controller=self.controller,
                name=self._name,
                config_dir=config_dir,
                output_dir=output_dir,
            )
            self.device = self.deployment_controller.device
            self._client = self.deployment_controller.client
        else:
            if device is None:
                raise ValueError(f"Plate {name} needs a config_dir or a device")
            self.deployment_controller = None
            self.device = device
            self._client = device_factory.create_client(device)

        self.screen_controller = ScreenController(
            controller=self.controller,
            client=self.client,
            device=self.device,
        )

        self.scheduler = PageScheduler(controller=self.controller, plate=self, config=self._config.focus)

    async def set_keep_awake(self, keep_awake: bool):
        """Keeps the screen on (no idle dimming), or restores the idle timeouts. The PageScheduler calls this."""
        self.controller.logger.info(f"{'Keeping' if keep_awake else 'No longer keeping'} the screen of plate {self._name} on")
        if keep_awake:
            await self.set_gui_config2(idle1=15, idle2=0)
            await self.screen_controller.set_idle(state="short")
        else:
            defaults = self.gui_defaults
            await self.set_gui_config(idle1=defaults.idle1, idle2=defaults.idle2)
            await self.set_gui_config2(idle1=defaults.idle1, idle2=defaults.idle2)
            await self.screen_controller.set_idle(state="off")

    @property
    def client(self) -> OpenHaspClient:
        return self._client

    @property
    def gui_defaults(self) -> GuiDefaults:
        """The idle timeouts: from the PlateConfig, or from the device's config."""
        if self._config.gui is not None:
            return self._config.gui
        gui = self.device.config.gui
        return GuiDefaults(idle1=gui.idle1, idle2=gui.idle2)

    @property
    def screen(self) -> Screen:
        """The screen size for code-defined layouts: from the PlateConfig, or from the device's config."""
        if self._config.screen is not None:
            return self._config.screen
        screen = self.device.config.openhasp_config_manager.device.screen
        return Screen(width=screen.width, height=screen.height)

    def add_page(self, page: PageController) -> PageController:
        self.controller.logger.info(f"Adding page '{page.__class__.__name__}' at index {page.index} to plate {self._name}")
        self.pages[page.index] = page
        return page

    def has_page(self, page: PageController) -> bool:
        return page in self.pages.values()

    def create_page(self, index: int) -> PageController:
        page = PageController(
            controller=self.controller,
            plate=self,
            state_updater=self.state_updater,
            index=index,
        )
        self.pages[index] = page
        return page

    async def init(self):
        await self.screen_controller.init()
        await self.setup_auto_brightness()

        self.controller.logger.info(f"Initializing {len(self.pages)} pages for plate {self._name}...")

        for page in self.pages.values():
            self.controller.logger.info(f"Initializing page {page.index} for plate {self._name}")
            await self._declare_objects(page)
            self.render_layout(page)
            await self.push_layout(page)
            self.controller.logger.info(f"Initializing objects for page {page.index} for plate {self._name}")
            await page.initialize_objects()

        await self.set_navigation()
        await self.scheduler.start()

    async def _declare_objects(self, page: PageController):
        """build_layout() and its mount, then register_objects()."""
        layout = await page.build_layout()
        if layout is not None:
            await layout.expand()
            if not layout.external:
                layout.layout(self.screen.width, self.screen.height)
            await layout.mount(page)
        await page.register_objects()
        if not page.objects:
            raise ValueError(f"Page {page.index} ({page.__class__.__name__}) of plate {self._name} declares no objects")

    def render_layout(self, page: PageController):
        """Renders the owned objects of a page into JSONL objects (in memory), see render_page()."""
        screen = self.screen
        rendered = render_page(page, self._config.theme, self.device.config, screen.width, screen.height)
        if rendered:
            self.rendered[page.index] = rendered
            if self._layout_dump_dir is not None:
                declarations = {o.obj_id: o.declaration for o in page.objects.values()}
                path = write_dump(self._layout_dump_dir, self._name, page.index, rendered, declarations)
                self.controller.logger.info(f"Layout of page {page.index} written to {path}")

    async def push_layout(self, page: Optional[PageController] = None):
        """
        Clears the owned pages and sends their rendered objects to the plate, over MQTT (they live in the plate's RAM until
        it reboots). Clearing removes what a previous layout left, and objects from flash a plate's boot.cmd may have put
        on the page: an update of an existing object can't change its type.
        :param page: the page to push; default: all owned pages
        """
        indices = [page.index] if page is not None else list(self.rendered)
        for index in indices:
            objects = self.rendered.get(index)
            if not objects:
                continue
            self.controller.logger.info(f"Pushing the layout of page {index} ({len(objects)} objects) to plate {self._name}")
            await self.client.clear_page(index)
            for payload in batch_lines(objects):
                await self.client.jsonl(payload)
        pages = [page] if page is not None else list(self.pages.values())
        for p in pages:
            for obj in p.objects.values():
                obj.live = True

    async def set_navigation(self):
        """
        Lets swiping cycle through the plate's pages (except page 0) in the order of their indices, wrapping around: sets
        `prev` and `next` of every page to its neighbours. This also overrides what JSONL files on flash set (e.g. a
        navbar's `next` of its last page), so code-defined pages added to a plate are reachable. Only for plates with
        code-defined pages, unless PlateConfig.wrap_navigation is off.
        """
        if not self._config.wrap_navigation or not self.rendered:
            return
        indices = sorted(index for index in self.pages if index > 0)
        if len(indices) < 2:
            return
        for position, index in enumerate(indices):
            previous, following = indices[position - 1], indices[(position + 1) % len(indices)]
            await self.client.set_object_properties(obj=f"p{index}b0", properties={"prev": previous, "next": following})

    async def setup_auto_brightness(self):
        if self.screen_controller._screen_brightness_task is not None:
            try:
                self.screen_controller._screen_brightness_task.cancel()
            except Exception:
                pass
            finally:
                self._screen_brightness_task = None

        async def _on_status_event(event_topic: str, event_payload: bytes):
            event_payload = event_payload.decode("utf-8")
            if event_payload == "off":
                self.controller.logger.debug(f"Activating screen, due to state/idle event: {event_payload}")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_default.on,
                    brightness=self._config.screen_brightness_default.brightness,
                )
            elif event_payload == "short":
                self.controller.logger.debug("Device idle for short time")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_short_idle.on,
                    brightness=self._config.screen_brightness_short_idle.brightness,
                )
            elif event_payload == "long":
                self.controller.logger.debug("Device idle for long time")
                await self.screen_controller.set_backlight(
                    state=self._config.screen_brightness_long_idle.on,
                    brightness=self._config.screen_brightness_long_idle.brightness,
                )
            else:
                self.controller.logger.warning(f"Got unexpected state/idle event: {event_topic} - {event_payload}")

        self._screen_brightness_task = await self.listen_openhasp_event(path="state/idle", callback=_on_status_event)

    async def sync(self):
        for page in self.pages.values():
            for obj in page.objects.values():
                obj.clear_cache()
        await self.state_updater.sync()

    async def reboot(self):
        """
        Reboots the device
        """
        return await self.client.reboot()

    async def wakeup(self):
        """
        Wakes up the display
        """
        # TODO: this currently wakes up the display indefinitely, it would be nice to be able
        #  to set a timeout after which the display goes back to sleep / default behavior
        return await self.screen_controller.set_idle(state="off")

    async def command(self, cmd: str, params: str = ""):
        return await self.client.command(
            keyword=cmd,
            params=params,
        )

    async def change_page(self, index: int):
        return await self.client.set_page(index)

    async def set_gui_config2(
        self, idle1: int = None, idle2: int = None, rotate: int = None, cursor: int = None, bckl: int = None
    ):
        """
        Publishes UI config via the Webserver REST API to the OpenHASP plate.
        Only the parameters that are not None will be set, the rest will be left unchanged.
        :param idle1:
        :param idle2:
        :param rotate:
        :param cursor:
        :param bckl:
        :return:
        """
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
        await self.client.set_gui_config(gui_config)

    async def set_gui_config(
        self, idle1: int = None, idle2: int = None, rotate: int = None, cursor: int = None, bckl: int = None
    ):
        """
        Publishes UI config via MQTT to the OpenHASP plate.
        Only the parameters that are not None will be set, the rest will be left unchanged.

        :param idle1:
        :param idle2:
        :param rotate:
        :param cursor:
        :param bckl:
        """
        parameters = {
            "idle1": idle1,
            "idle2": idle2,
            "rotate": rotate,
            "cursor": cursor,
            "bckl": bckl,
        }
        # ignore keys with None value
        parameters = {k: v for k, v in parameters.items() if v is not None}

        return await self._set_config(submodule="gui", parameters=parameters)

    async def _set_config(self, submodule: str, parameters: Dict):
        self.controller.logger.info(f"Setting {submodule} config: {parameters}")
        return await util_openhasp.config(
            controller=self.controller,
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
        # return await self.react_to(
        #     triggers=EventTrigger(
        #         controller=self.controller,
        #         plate=self._name,
        #         path=path,
        #     ),
        #     action=callback,
        # )
        return await util_openhasp.listen_event(
            controller=self.controller,
            client=self.client,
            path=path,
            callback=callback,
        )
