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
        entity: str = None,
        get_state: Callable[[], Awaitable[bool]] = None,
    ):
        """
        Sets up a connection between a toggle and a light entity

        See: https://www.openhasp.com/0.7.0/design/objects/switch/

        :param app: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity: (optional) the entity id of the light
        :param get_state: (optional) called to get the current state of the toggle, should return "on" or "off"
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self.entity = entity
        self.get_state = get_state

    async def init(self):
        self.app.log(f"Initializing switch object {self.object_id}", level="DEBUG")
        await self._setup_switch(
            entity=self.entity,
        )

    async def _setup_switch(self, entity: str):
        # TODO: make this optional and support custom on_changed and on_released callbacks instead of just toggle

        async def _toggle_callback(topic: str, payload: Dict):
            self.app.log(f"Toggle callback payload: {payload}")
            if payload["event"] == SwitchEvent.UP:
                en = self.app.get_entity(entity=entity)
                self.app.log(f"Toggle '{en.entity_name}'")
                await self.app.call_service("homeassistant/toggle", entity_id=en.entity_id)

        await self.listen_obj(
            callback=_toggle_callback,
        )

        async def _state_update_callback(entity, attribute, old, new, kwargs):
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

        async def get_toggle_state() -> str:
            return await self.app.get_state(entity)

        async def set_toggle_obj_state(state: str):
            await _state_update_callback(None, None, None, state, None)

        toggle_sync_name = f"toggle:{self.object_id}:{entity}"
        self.state_updater.register(
            name=toggle_sync_name,
            get_state=get_toggle_state,
            update_obj=set_toggle_obj_state,
        )
        await self.state_updater.sync(toggle_sync_name)

        await util_ad.listen_state_and_call_immediately(
            controller=self.app,
            callback=_state_update_callback,
            entity_id=entity
        )

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
