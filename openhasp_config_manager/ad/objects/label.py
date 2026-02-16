from typing import Callable, Awaitable, Any, List, TYPE_CHECKING

from appdaemon import ADAPI

from openhasp_config_manager.ad import STATE_UNKNOWN, STATE_UNAVAILABLE, util_ad
from openhasp_config_manager.ad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater
else:
    StateUpdater = Any


class LabelObjectController(ObjectController):
    """
    Controller for a label object on the OpenHASP plate.
    """

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        entity_id: str | List[str] = None,
        attribute: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        converter: Callable[[Any], str] = None,
    ):
        """
        Sets up a connection between an object and an entity, updating the text of the object
        each time the entity changes based on the text function.

        See: https://www.openhasp.com/latest/design/objects/label/

        :param app: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: (optional) the entity id
        :param attribute: (optional) the attribute from the entity to use
        :param get_state: (optional) function to get the current state
        :param converter: (optional) converter function to transform the state value into the displayed text
        """
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_ids = entity_id if isinstance(entity_id, list) else [entity_id] if entity_id is not None else None
        self._attribute = attribute
        self._get_state = get_state
        self._converter = converter
        if self._converter is None:
            self._converter = lambda x: str(x) if x is not None else "-"

    async def init(self):
        self.app.log(f"Initializing label object {self.object_id} for entity {self._entity_ids}", level="DEBUG")

        if self._entity_ids is not None or self._get_state is not None:
            await self._setup_state_listeners_and_sync()

    async def _setup_state_listeners_and_sync(self):
        ids_str = ",".join(self._entity_ids) if self._entity_ids else "None"
        text_sync_name = f"label:{self.object_id}:{ids_str}"
        self.state_updater.register(
            name=text_sync_name,
            get_state=self.__get_text_state,
            update_obj=self.__set_text_obj_state,
        )
        await self.state_updater.sync(name=text_sync_name)

        if self._entity_ids is not None:
            if self._attribute is not None:
                for entity_id in self._entity_ids:
                    await util_ad.listen_state_and_call_immediately(
                        controller=self.app, callback=self._on_state_changed, entity_id=entity_id, attribute=self._attribute
                    )
            else:
                for entity_id in self._entity_ids:
                    await util_ad.listen_state_and_call_immediately(
                        controller=self.app, callback=self._on_state_changed, entity_id=entity_id
                    )

    async def __get_text_state(self) -> str:
        if self._get_state is not None:
            return await self._get_state()

        if self._attribute is not None:
            return await self.app.get_state(self._entity_ids[0], attribute=self._attribute)
        else:
            return await self.app.get_state(self._entity_ids[0])

    async def __set_text_obj_state(self, state: Any):
        await self._on_state_changed(None, None, None, state, None)

    async def _on_state_changed(self, entity, attribute, old, new, kwargs):
        if self._get_state is not None:
            new = await self._get_state()
        if new in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            new = "-"

        display_text = self._converter(new)
        await self.set_text(
            text=display_text,
        )

    async def set_text(self, text: str):
        """
        Sets the text for this text object
        :param text: the text to set
        """
        return await self.client.set_text(obj=self.object_id, text=text)

    async def set_color(self, color: str):
        """
        Sets the text color for this text object
        :param color: the color to set as hex string, for example "#FF0000"
        """
        return await self.set_object_properties(
            properties={"text_color": color},
        )

    async def set_mode(self, mode: str):
        """
        The wrapping mode of long text labels:

        `expand` Expand the object size to the text size
        `break` Keep the object width, break the too long lines and expand the object height
        `dots` Keep the size and write dots at the end if the text is too long
        `scroll` Keep the size and roll the text back and forth
        `loop` Keep the size and roll the text circularly
        `crop` Keep the size and crop the text out of it

        See: https://www.openhasp.com/latest/design/objects/label/

        :param mode: the mode to set
        """
        return await self.set_object_properties(
            properties={"mode": mode},
        )

    async def set_border_width(self, width: int = 0):
        """
        Sets the border width for this text object
        :param width: the width to set in pixels
        """
        return await self.set_object_properties(
            properties={"border_width": width},
        )
