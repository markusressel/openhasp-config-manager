from enum import StrEnum
from typing import Dict, Callable, Awaitable, Any, TYPE_CHECKING

from appdaemon import ADAPI

from openhasp_config_manager.ad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater
else:
    StateUpdater = Any


class SliderEvent(StrEnum):
    CHANGED = "changed"
    UP = "up"

class SliderObjectController(ObjectController):

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        get_state: Callable[[], Awaitable[Any]],
        on_changed: Callable[[Any], Awaitable[None]],
        on_released: Callable[[Any], Awaitable[None]],
    ):
        """
        Sets up a connection between a slider and a media player entity
        :param get_state: called to get the current state of the slider
        :param on_changed: called when the slider is changed
        :param on_released: called when the slider is released
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self.get_state = get_state
        self.on_changed = on_changed
        self.on_released = on_released

    async def init(self):
        self.app.log(f"Initializing slider object {self.object_id}", level="DEBUG")

        # TODO: utilize get_state

        async def _even_callback(topic: str, payload: Dict):
            value = payload["val"]
            if payload["event"] == SliderEvent.CHANGED:
                await self.on_changed(value)
            elif payload["event"] == SliderEvent.UP:
                await self.on_released(value)

        await self.listen_obj(
            callback=_even_callback,
        )

    async def set_value(self, value: int):
        """
        Sets the value for this slider object
        :param value: the value to set
        """
        await self.set_object_properties(
            properties={
                "val": value,
            }
        )

    async def set_min_max(self, min: int, max: int):
        """
        Sets the min and max for this slider object
        :param min: the min value
        :param max: the max value
        """
        await self.set_object_properties(
            properties={
                "min": min,
                "max": max,
            }
        )

    async def set_min_allowed(self, min: int):
        """
        Sets the minimal allowed value of the indicator
        :param min: the min value
        """
        await self.set_object_properties(
            properties={
                "start_value": min,
            }
        )
