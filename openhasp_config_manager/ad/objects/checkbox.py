from typing import Callable, TYPE_CHECKING, Any, Awaitable

from appdaemon import ADAPI

from openhasp_config_manager.ad import STATE_UNKNOWN, STATE_UNAVAILABLE, util_ad
from openhasp_config_manager.ad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater
else:
    StateUpdater = Any


class CheckboxObjectController(ObjectController):
    """
    Controller for a checkbox object on the OpenHASP plate.
    """

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        entity_id: str = None,
        attribute: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        converter: Callable[[Any], str] = lambda x: str(x)
    ):
        """
        Sets up a connection between an object and an entity, updating the text of the object
        each time the entity changes based on the text function.

        See: https://www.openhasp.com/latest/design/objects/checkbox/

        :param app: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: the entity id
        :param attribute: the attribute from the entity to use
        :param get_state: function to get the current state of the checkbox
        :param converter: the function to call to get the text to set
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_id = entity_id
        self._attribute = attribute
        self._get_state = get_state
        self._converter = converter

    async def init(self):
        self.app.log(f"Initializing checkbox object {self.object_id} for entity {self._entity_id}", level="DEBUG")

        if self._entity_id is not None or self.__get_checkbox_state is not None:
            await self._setup_state_listener_and_sync()

    async def _setup_state_listener_and_sync(self):
        text_sync_name = f"checkbox:{self.object_id}:{self._entity_id}"
        self.state_updater.register(
            name=text_sync_name,
            get_state=self.__get_checkbox_state,
            update_obj=self.__set_checkbox_obj_state,
        )
        await self.state_updater.sync(text_sync_name)

        if self._entity_id is not None:
            if self._attribute is not None:
                await util_ad.listen_state_and_call_immediately(
                    controller=self.app, callback=self._on_state_changed, entity_id=self._entity_id, attribute=self._attribute)
            else:
                await util_ad.listen_state_and_call_immediately(
                    controller=self.app, callback=self._on_state_changed, entity_id=self._entity_id)

    async def __get_checkbox_state(self) -> str:
        """
        Gets the current state of the checkbox object based on the entity and attribute (if specified)
        """
        if self._get_state is not None:
            return await self._get_state()
        if self._attribute is not None:
            return await self.app.get_state(self._entity_id, attribute=self._attribute)
        else:
            return await self.app.get_state(self._entity_id)

    async def __set_checkbox_obj_state(self, state: str):
        await self._on_state_changed(None, None, None, state, None)

    async def _on_state_changed(self, entity, attribute, old, new, kwargs):
        if new in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            await self.set_enabled(False)
            return
        await self.set_enabled(True)
        await self.set_text(
            text=self._converter(new),
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
