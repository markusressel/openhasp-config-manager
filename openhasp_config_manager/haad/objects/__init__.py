from typing import Dict, Callable, Awaitable, Any

from controller import HaadController
from openhasp_config_manager.haad.page.state_updater import StateUpdater
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


class ObjectController:
    """
    Base class for controllers for objects on the OpenHASP plate.
    This should be subclassed for each type of object to implement specific functionality for that object type.
    """

    def __init__(
        self,
        controller: HaadController,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
    ):
        """
        Object controller for a single object on a page on an OpenHASP plate.

        :param controller: the HaadController instance
        :param client: the OpenHASP client to use for communication with the plate
        :param state_updater: the state updater to use for registering state updates
        :param page: the page index of the object
        :param obj_id: the object index of the object
        """
        self.controller = controller
        self.client = client
        self.state_updater = state_updater
        self.page = page
        self.obj_id = obj_id
        self._last_properties: Dict[str, Any] = {}

    def clear_cache(self):
        """
        Clears the properties cache, forcing the next property update to be sent to the device.
        """
        self._last_properties.clear()

    @property
    def object_id(self):
        """
        :return: the composite object id for this object, in the format "p{page}b{obj_id}"
        """
        return f"p{self.page}b{self.obj_id}"

    async def init(self):
        """
        Initializes the object controller. This should be called after the object is created and registered on the page.
        """
        raise NotImplementedError()

    async def set_hidden(self, hidden: bool):
        """
        Hides or shows this slider object
        :param hidden: whether to hide or show the slider
        """
        return await self.client.set_hidden(
            obj=self.object_id,
            hidden=hidden,
        )

    async def set_enabled(self, enabled: bool):
        """
        Enables or disables this slider object
        :param enabled: whether to enable or disable the slider
        """
        await self.set_object_properties(
            properties={
                "enabled": enabled,
            }
        )

    async def set_object_properties(self, properties: Dict, force: bool = False):
        """
        Sets the properties of an object on the plate of this controller
        :param properties: the properties to set
        :param force: if True, bypasses deduplication, and forces the properties to be sent
        """
        changed_properties = {}
        for k, v in properties.items():
            if force or k not in self._last_properties or self._last_properties[k] != v:
                changed_properties[k] = v
                
        if not changed_properties:
            return
            
        for k, v in changed_properties.items():
            self._last_properties[k] = v

        self.controller.logger.debug(f"Setting properties of {self.object_id}: {changed_properties}")
        return await self.client.set_object_properties(
            obj=self.object_id,
            properties=changed_properties,
        )

    async def listen_obj(self, callback: Callable[[str, Dict], Awaitable[Any]]):
        """
        Listens to events for the given object on the given page and calls the callback with it
        :param callback: the callback to call when an event for the given object is received
        """
        from openhasp_config_manager.haad import util_openhasp

        return await util_openhasp.listen_state(
            controller=self.controller,
            client=self.client,
            obj=self.object_id,
            callback=callback,
        )
