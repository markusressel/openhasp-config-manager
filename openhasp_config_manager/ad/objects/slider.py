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
        entity_id: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        on_changed: Callable[[Any], Awaitable[None]] = None,
        on_released: Callable[[Any], Awaitable[None]] = None,
        transform_value: Callable[[Any], int] = None,
    ):
        """
        Sets up a connection between a slider and a media player entity

        See: https://www.openhasp.com/0.7.0/design/objects/slider/

        :param app: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: (optional) the entity id to use for values
        :param get_state: (optional) called to get the current state of the slider
        :param on_changed: (optional) called when the slider is changed
        :param on_released: (optional) called when the slider is released
        :param transform_value: (optional) a function to transform the entity value to a slider value
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_id = entity_id
        self._get_state = get_state
        self._on_changed = on_changed
        self._on_released = on_released
        self._transform_value = transform_value
        if transform_value is None:

            def __default_transform_value(x: Any) -> int:
                if isinstance(x, str):
                    x = x.replace("%", "").strip()
                return int(float(x))

            self._transform_value = __default_transform_value

    async def init(self):
        self.app.log(f"Initializing slider object {self.object_id}", level="DEBUG")

        if self._entity_id is not None or self._get_state is not None:
            await self._setup_state_listener_and_sync()

    async def _setup_state_listener_and_sync(self):
        slider_sync_name = f"slider:{self.object_id}:{self._entity_id}"
        self.state_updater.register(
            name=slider_sync_name,
            get_state=self.__get_slider_state,
            update_obj=self.__set_slider_obj_state,
        )
        await self.state_updater.sync(slider_sync_name)

        async def _even_callback(topic: str, payload: Dict):
            value = payload["val"]
            if payload["event"] == SliderEvent.CHANGED:
                if self._on_changed is not None:
                    await self._on_changed(value)
            elif payload["event"] == SliderEvent.UP:
                if self._on_released is not None:
                    await self._on_released(value)

        await self.listen_obj(
            callback=_even_callback,
        )

    async def __get_slider_state(self) -> str:
        """
        Gets the current state to be used for the value of this slider object, either by calling get_state or by getting the state of the entity.
        :return: the current state to be used for the value of this slider object
        """
        if self._get_state is not None:
            return await self._get_state()
        else:
            return await self.app.get_state(self._entity_id)

    async def __set_slider_obj_state(self, state: str):
        await self.set_value(state)

    async def set_value(self, value: str | int):
        """
        Sets the value for this slider object
        :param value: the value to set
        """
        await self.set_object_properties(
            properties={
                "val": self._transform_value(value),
            }
        )

    async def set_min_max(self, minimum: int, maximum: int):
        """
        Sets the min and max for this slider object
        :param minimum: the min value
        :param maximum: the max value
        """
        await self.set_object_properties(
            properties={
                "min": minimum,
                "max": maximum,
            }
        )

    async def set_min_allowed(self, minimum: int):
        """
        Sets the minimal allowed value of the indicator
        :param minimum: the min value
        """
        await self.set_object_properties(
            properties={
                "start_value": minimum,
            }
        )
