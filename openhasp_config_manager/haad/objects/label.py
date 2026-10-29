from typing import Callable, Awaitable, Any, List, Sequence, TYPE_CHECKING

from haad.controller import HaadController
from openhasp_config_manager.haad import STATE_UNKNOWN, STATE_UNAVAILABLE
from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

from haad import HaadStateEvent
from haad.triggers import EntityTrigger
from haad.triggers.resolver import TriggerInput

if TYPE_CHECKING:
    from openhasp_config_manager.haad.page import EntityRef
    from openhasp_config_manager.haad.page.state_updater import StateUpdater
else:
    StateUpdater = Any


class LabelObjectController(ObjectController):
    """
    Controller for a label object on the OpenHASP plate.
    """

    OBJ_TYPE = "label"

    def __init__(
        self,
        controller: HaadController,
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

        :param controller: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: (optional) the entity id
        :param attribute: (optional) the attribute from the entity to use
        :param get_state: (optional) function to get the current state
        :param converter: (optional) converter function to transform the state value into the displayed text
        """
        super().__init__(controller=controller, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_ids = entity_id if isinstance(entity_id, list) else [entity_id] if entity_id is not None else None
        self._attribute = attribute
        self._get_state = get_state
        self._converter = converter
        if self._converter is None:
            self._converter = lambda x: str(x) if x is not None else "-"
        self._initialized = False

    async def bind_text(
        self,
        entity: "EntityRef | Sequence[EntityRef]" = None,
        attribute: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        text: Callable[[Any], str] = None,
        trigger: TriggerInput = None,
    ):
        """
        Binds the text of a label that was declared without a binding, e.g. an object of a `Part`
        (`part.obj(10, LabelObjectController)`), like the arguments of PageController.add_label() do. Call it before the
        objects of the page are initialized, i.e. in register_objects().
        :param entity: the entity (or entities) to bind to, as HAEntity or entity id
        :param attribute: (optional) the attribute to bind to
        :param get_state: (optional) a function to get the current state, instead of the entity's
        :param text: (optional) a function that takes the state and returns the text; default: the label's (the state as text)
        :param trigger: (optional) refreshes the text (from get_state) whenever it fires
        :raises RuntimeError: if the label is initialized already
        :raises ValueError: if the label is bound already, or neither `entity` nor `get_state` is given
        """
        from openhasp_config_manager.haad.page import entity_ids

        if self._initialized:
            raise RuntimeError(f"{self.object_id} is initialized already: bind its text in register_objects()")
        if self._entity_ids is not None or self._get_state is not None:
            raise ValueError(f"The text of {self.object_id} is bound already")
        if entity is None and get_state is None:
            raise ValueError(f"Binding the text of {self.object_id} needs an entity or get_state")
        ids = entity_ids(entity)
        self._entity_ids = ids if isinstance(ids, list) else [ids] if ids is not None else None
        self._attribute = attribute
        self._get_state = get_state
        if text is not None:
            self._converter = text
        if trigger is not None:
            self.trigger = trigger

    async def init(self):
        self._initialized = True
        self.controller.logger.debug(f"Initializing label object {self.object_id} for entity {self._entity_ids}")

        if self._entity_ids is not None or self._get_state is not None:
            await self._setup_state_listeners_and_sync()

    async def _setup_state_listeners_and_sync(self):
        ids_str = ",".join(self._entity_ids) if self._entity_ids else "None"
        text_sync_name = f"label:{self.object_id}:{ids_str}"
        self.register_state(
            name=text_sync_name,
            get_state=self.__get_text_state,
            update_obj=self.__set_text_obj_state,
        )
        await self.state_updater.sync(name=text_sync_name)

        if self._entity_ids is not None:
            if self._attribute is not None:
                for entity_id in self._entity_ids:
                    await self.react_to(
                        trigger=EntityTrigger(entities=entity_id, attribute=self._attribute),
                        action=self._on_state_changed,
                        immediately=True,
                    )
            else:
                for entity_id in self._entity_ids:
                    await self.react_to(
                        trigger=EntityTrigger(entities=entity_id),
                        action=self._on_state_changed,
                        immediately=True,
                    )

    async def __get_text_state(self) -> str:
        if self._get_state is not None:
            return await self._get_state()

        if self._attribute is not None:
            return await self.controller.ha.get_state(self._entity_ids[0], attribute=self._attribute)
        else:
            return await self.controller.ha.get_state(self._entity_ids[0])

    async def __set_text_obj_state(self, state: Any):
        await self._on_state_changed(HaadStateEvent(None, None, None, state, None))

    async def _on_state_changed(self, event: HaadStateEvent):
        new = event.new
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
        return await self.send_properties({"text": text})

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
