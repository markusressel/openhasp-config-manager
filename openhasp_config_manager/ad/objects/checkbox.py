from typing import Callable, TYPE_CHECKING, Any

from appdaemon import ADAPI

from openhasp_config_manager.ad import STATE_UNKNOWN, STATE_UNAVAILABLE, util_ad
from openhasp_config_manager.ad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page import StateUpdater
else:
    StateUpdater = Any


class CheckboxObjectController(ObjectController):

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        entity: str,
        attribute: str = None,
        converter: Callable = lambda x: str(x)
    ):
        """
        Sets up a connection between an object and an entity, updating the text of the object
        each time the entity changes based on the text function.
        :param entity: the entity id
        :param attribute: the attribute from the entity to use
        :param converter: the function to call to get the text to set
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self.entity = entity
        self.attribute = attribute
        self.converter = converter

    async def init(self):
        self.app.log(f"Initializing checkbox object {self.object_id} for entity {self.entity}", level="DEBUG")
        text_sync_name = f"checkbox:{self.object_id}:{self.entity}"
        self.state_updater.register(
            name=text_sync_name,
            get_state=self.get_text_state,
            update_obj=self.set_text_obj_state,
        )
        await self.state_updater.sync(text_sync_name)

        if self.attribute is not None:
            await util_ad.listen_state_and_call_immediately(
                controller=self.app, callback=self._on_state_changed, entity_id=self.entity, attribute=self.attribute)
        else:
            await util_ad.listen_state_and_call_immediately(
                controller=self.app, callback=self._on_state_changed, entity_id=self.entity)

    async def get_text_state(self) -> str:
        if self.attribute is not None:
            return await self.app.get_state(self.entity, attribute=self.attribute)
        else:
            return await self.app.get_state(self.entity)

    async def set_text_obj_state(self, state: str):
        await self._on_state_changed(None, None, None, state, None)

    async def _on_state_changed(self, entity, attribute, old, new, kwargs):
        if new in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            await self.set_enabled(False)
            return
        await self.set_enabled(True)
        await self.set_text(
            text=self.converter(new),
        )

    async def set_text(self, text: str):
        """
        Sets the text for this text object
        :param text: the text to set
        """
        return await self.set_object_properties(
            properties={"text": text},
        )

    async def set_is_checked(self, is_checked: bool):
        """
        Sets whether this checkbox object is checked or not
        :param is_checked: True if this checkbox object is checked, False if it is unchecked.
        """
        await self.set_object_properties(
            properties={
                "val": 1 if is_checked else 0,
            }
        )
