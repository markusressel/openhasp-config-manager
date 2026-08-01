from typing import Callable, Any, TYPE_CHECKING, Awaitable

from controller import HaadController
from openhasp_config_manager.haad import STATE_UNKNOWN, STATE_UNAVAILABLE
from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

from haad import HaadStateEvent

if TYPE_CHECKING:
    from openhasp_config_manager.haad.page.state_updater import StateUpdater
else:
    StateUpdater = Any


class BarObjectController(ObjectController):
    """
    Controller for a bar object on the OpenHASP plate.
    """

    def __init__(
        self,
        controller: HaadController,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        entity_id: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        transform_value: Callable[[Any], int] = None,
    ):
        """
        Sets up a connection between a progress bar and an entity

        See: https://www.openhasp.com/0.7.0/design/objects/bar/

        :param controller: the app this object belongs to
        :param client: the OpenHASP client
        :param state_updater: the state updater to use
        :param page: the page id
        :param obj_id: the object id
        :param entity_id: the entity id to use for values
        :param transform_value: (optional) a function to transform the entity value to a progress value
        """
        super().__init__(controller=controller, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self._entity_id = entity_id
        self._get_state = get_state
        self._transform_value = transform_value
        if transform_value is None:

            def __default_transform_value(x: Any) -> int:
                if isinstance(x, str):
                    x = x.replace("%", "").strip()
                return int(float(x))

            self._transform_value = __default_transform_value

    async def init(self):
        self.controller.logger.debug(f"Initializing progress object {self.object_id} for entity {self._entity_id}")

        if self._entity_id is not None or self._get_state is not None:
            await self._setup_state_listener_and_sync()

    async def _setup_state_listener_and_sync(self):
        progress_sync_name = f"progress:{self.object_id}:{self._entity_id}"
        self.state_updater.register(
            name=progress_sync_name,
            get_state=self.__get_progress_state,
            update_obj=self.__set_progress_obj_state,
        )
        await self.state_updater.sync(progress_sync_name)

        if self._entity_id is not None:
            await self.controller.react_to(
                trigger=self._entity_id,
                action=self.__on_state_changed,
                immediately=True,
            )

    async def __on_state_changed(self, event: HaadStateEvent):
        if event.new in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            await self.set_enabled(False)
            return
        await self.set_enabled(True)
        await self.set_progress(event.new)

    async def __get_progress_state(self) -> str:
        """
        Gets the current state to be used for the progress of this progress object, either by calling get_state or by getting the state of the entity.
        :return: the current state to be used for the progress of this progress object
        """
        if self._get_state is not None:
            return await self._get_state()
        elif self._entity_id is not None:
            return await self.controller.ha.get_state(self._entity_id)
        else:
            return None

    async def __set_progress_obj_state(self, state: str):
        await self.__on_state_changed(HaadStateEvent(None, None, None, state, None))

    async def set_progress(self, progress: str | int):
        """
        Sets the progress for this progress object
        :param progress: the progress to set
        """
        await self.set_object_properties(
            properties={
                "val": self._transform_value(progress),
            }
        )

    async def set_min_max(self, minimum: int, maximum: int):
        """
        Sets the min and max for this progress object
        :param minimum: the min value
        :param maximum: the max value
        """
        await self.set_object_properties(
            properties={
                "min": minimum,
                "max": maximum,
            }
        )
