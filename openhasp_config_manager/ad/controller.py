import asyncio
import traceback
from typing import Dict

from appdaemon import ADAPI

from openhasp_config_manager.ad import KEY_ARGS, KEY_NAME, util_ad_timer
from openhasp_config_manager.ad.page.state_updater import StateUpdater
from openhasp_config_manager.ad.plate import PlateConfig, PlateController

PLATE_SETUP_TIMER = "plate_setup_timer"
PLATE_SYNC_TIMER = "plate_sync_timer"


class OpenHaspController(ADAPI):

    def __init__(self, ad, config_model):
        super().__init__(ad, config_model)
        self._lwt_task = None

    @property
    def plate_config(self) -> PlateConfig:
        return PlateConfig()

    async def initialize(self):
        self._name = self.args[KEY_ARGS][KEY_NAME]
        self.log(f"Initializing {self._name}...")

        self.state_updater = StateUpdater(app=self)
        self.plate_controller = PlateController(
            app=self,
            state_updater=self.state_updater,
            name=self._name,
            config=self.plate_config,
        )

        await self.before_setup_plate()

    async def before_setup_plate(self):
        await self.setup_online_state_listener()
        await self.schedule_plate_setup()

    async def terminate(self):
        """
        Called by AppDaemon when the app is being terminated.
        """
        self.log(f"Terminating {self._name}...")
        if self._lwt_task is not None:
            self._lwt_task.cancel()
            self._lwt_task = None
        await self.teardown_plate_setup()

    async def teardown_plate_setup(self):
        self.state_updater.clear()
        await util_ad_timer.cancel_all(self)

    async def schedule_plate_setup(self):
        """
        Schedules the initial setup of a plate when it comes online for the
        first time (as seen by this app).
        """
        await util_ad_timer.schedule(
            controller=self,
            name=PLATE_SETUP_TIMER,
            callback=self.__failsafe_plate_setup,
            delay=1
        )

    async def __failsafe_plate_setup(self, kwargs: Dict):
        timeout = 10

        # ensure the plate is online
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, self.__online_check)
        if not res:
            self.log(f"Plate '{self._name}' is not online yet, retrying in {timeout}...")
            await util_ad_timer.schedule(self, PLATE_SETUP_TIMER, self.__failsafe_plate_setup, timeout)
            return

        try:
            self.log(f"Setting up plate '{self._name}'...")
            await self.setup_plate()
            self.log(f"Initializing plate controller for '{self._name}'...")
            await self.plate_controller.init()
            self.log(f"Plate '{self._name}' setup complete, scheduling sync...")
            await self.schedule_sync()
            self.log(f"Plate '{self._name}' is now online and ready.")
        except Exception as ex:
            self.log(f"Exception during plate setup: {ex}", level="ERROR")
            tb = traceback.format_exc()
            self.log(
                f"Failed to setup plate '{self._name}', retrying in {timeout}: {type(ex)}: {ex} {tb}",
                level="ERROR")
            # await util_ad_timer.schedule(self, PLATE_SETUP_TIMER, self.__failsafe_plate_setup, timeout)

    def __online_check(self) -> bool:
        try:
            self.plate_controller.client.get_files()
            return True
        except Exception as ex:
            return False

    async def setup_plate(self):
        """
        Contains the logic to setup the plate when it comes online for the first time
        """
        raise NotImplementedError()
        # await self.set_gui_config(cursor=0)

    async def schedule_sync(self):
        await util_ad_timer.schedule(
            controller=self,
            name=PLATE_SYNC_TIMER,
            callback=self.__plate_sync_timer_callback,
            delay=1
        )

    async def __plate_sync_timer_callback(self, kwargs: Dict):
        await self.plate_controller.sync()

    async def setup_online_state_listener(self):
        if self._lwt_task is not None:
            # task already running
            return

        self.log(f"Setting up online state listener for {self._name}...")

        async def _on_lwt_event(event_topic: str, event_payload: bytes):
            event_payload = event_payload.decode("utf-8")
            self.log(f"Received LWT event for plate {self._name}: {event_payload}")
            if event_payload == "online":
                self.log(f"Reinitializing plate {self._name} due to online event")
                # await self.teardown_plate_setup()
                # await self.before_setup_plate()
                # await self.plate_controller.change_page(index=1)
                await self.schedule_sync()

        self._lwt_task = await self.plate_controller.listen_openhasp_event(
            path="LWT",
            callback=_on_lwt_event
        )

    # async def _setup_auto_deploy_when_online(self):
    #     async def _on_lwt_event(event_topic: str, event_payload: bytes):
    #         event_payload = event_payload.decode("utf-8")
    #         if event_payload == "online":
    #             self.app.log(f"Received online event for plate {self._name}, syncing state")
    #             await self.state_updater.sync()
    #             # try:
    #             #     changed = await self.deployment_controller.deploy(purge=True)
    #             #     if changed:
    #             #         self.app.log(f"Configuration changed, restarting plate")
    #             #         await self.reboot()
    #             # except Exception as ex:
    #             #     self.app.log(f"Error while deploying plate config: {ex}")
    #
    #     await self.listen_openhasp_event(path="LWT", callback=_on_lwt_event)

    def add_page(self, page_controller: 'PageController'):
        self.plate_controller.add_page(page_controller)
        return page_controller
