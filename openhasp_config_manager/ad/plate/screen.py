from asyncio import Task

from appdaemon import ADAPI

from openhasp_config_manager.ad.plate import DeploymentController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


class ScreenController:
    """
    Controller for the screen settings of the OpenHASP plate.
    """

    def __init__(self, app: ADAPI, client: OpenHaspClient, deployment_controller: DeploymentController):
        self.app = app
        self.client = client
        self.deployment_controller = deployment_controller

        self._screen_brightness_task: Task = None

    async def init(self):
        await self.set_default_auto_brightness_config()

    async def set_backlight(self, state: bool, brightness: int):
        """
        Sets the backlight state and brightness
        :param state: True to turn on, False to turn off
        :param brightness: the brightness level in 0..255
        """
        self.app.log(f"Setting backlight state to {'on' if state else 'off'} with brightness {brightness}")
        return await self.client.set_backlight(state=state, brightness=brightness)

    async def set_idle(self, state: str):
        """
        Forces the given idle state
        :param state: one of "off", "short", "long"
        """
        self.app.log(f"Setting idle state to '{state}'")
        return await self.client.set_idle_state(state)

    async def set_default_auto_brightness_config(self):
        self.deployment_controller.deploy_config()
