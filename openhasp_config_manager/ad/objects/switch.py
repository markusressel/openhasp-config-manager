from enum import StrEnum
from typing import Dict, TYPE_CHECKING, Any, Callable, Awaitable

from appdaemon import ADAPI

from openhasp_config_manager.ad import util_ad
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater
else:
    StateUpdater = Any
from openhasp_config_manager.ad.objects import ObjectController


class SwitchEvent(StrEnum):
    UP = "up"
    CHANGED = "changed"


class SwitchState(StrEnum):
    ON = "on"
    OFF = "off"


class SwitchObjectController(ObjectController):
    """
    Controller for a switch object on the OpenHASP plate.
    """

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        entity_id: str = None,
        get_state: Callable[[], Awaitable[bool]] = None,
    ):
        """
        Sets up a connection between a switch and a light entity

        See: https://www.openhasp.com/0.7.0/design/objects/switch/

        :param app: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: (optional) the entity id of the light
        :param get_state: (optional) called to get the current state of the switch, should return True for on and False for off
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_id = entity_id
        self._get_state = get_state

    async def init(self):
        self.app.log(f"Initializing switch object {self.object_id}", level="DEBUG")

        if self._entity_id is not None or self._get_state is not None:
            await self._setup_state_listener_and_sync()

    async def _setup_state_listener_and_sync(self):
        switch_sync_name = f"switch:{self.object_id}:{self._entity_id}"
        self.state_updater.register(
            name=switch_sync_name,
            get_state=self.__get_switch_state,
            update_obj=self.__set_switch_obj_state,
        )
        await self.state_updater.sync(switch_sync_name)

        async def _switch_callback(topic: str, payload: Dict):
            self.app.log(f"switch callback payload: {payload}")
            if payload["event"] == SwitchEvent.UP:
                if self._entity_id is not None:
                    await self._toggle_entity()

        await self.listen_obj(
            callback=_switch_callback,
        )

        if self._entity_id is not None:
            await util_ad.listen_state_and_call_immediately(
                controller=self.app,
                callback=self.__state_update_callback,
                entity_id=self._entity_id
            )

    async def _toggle_entity(self):
        en = self.app.get_entity(entity=self._entity_id)
        self.app.log(f"switch '{en.entity_name}'")
        await self.app.call_service("homeassistant/switch", entity_id=en.entity_id)

    async def __get_switch_state(self) -> bool:
        """
        Gets the current state of this switch object, either by calling get_state or by getting the state of the entity.
        :return: the current state of this switch object
        """
        if self._get_state is not None:
            return await self._get_state()
        elif self._entity_id is not None:
            state = await self.app.get_state(self._entity_id)
            return state == SwitchState.ON
        else:
            raise ValueError("No method to get state for this switch object")

    async def __state_update_callback(self, entity, attribute, old, new, kwargs):
        enabled = True
        val = 0
        if new == SwitchState.ON:
            val = 1
        elif new == SwitchState.OFF:
            val = 0
        else:
            enabled = False

        await self.set_object_properties(
            properties={
                "val": val,
                "enabled": enabled,
            }
        )

    async def __set_switch_obj_state(self, state: str):
        await self.__state_update_callback(None, None, None, state, None)

    async def set_indicator_color(self, color: str):
        """
        Sets the indicator color for this switch object
        :param color: the color to set as hex string, for example "#FF0000"
        """
        return await self.set_object_properties(
            properties={"bg_color10": color},
        )

    async def set_knob_color(self, color: str):
        """
        Sets the knob color for this switch object
        :param color: the color to set as hex string, for example "#FF0000"
        """
        return await self.set_object_properties(
            properties={"bg_color20": color},
        )

    async def set_knob_corner_radius(self, radius: int = 0):
        """
        Sets the knob corner radius for this switch object
        :param radius: the corner radius to set
        """
        return await self.set_object_properties(
            properties={"radius20": radius},
        )
