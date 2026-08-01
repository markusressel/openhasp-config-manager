from typing import Callable, Awaitable, Any

from haad.controller import HaadController


class StateUpdater:
    """
    Used as a registry to automatically update the state of objects based on the current state of entities
    within home assistant, when a plate becomes available
    """

    def __init__(self, controller: HaadController):
        self.controller = controller
        self._registered_objects = {}

    async def sync(self, name: str = None):
        """
        Sync the current state of all registered objects to the plate
        """
        if name is not None:
            item = self._registered_objects.get(name, None)
            if item is not None:
                entries_to_sync = {name: item}
            else:
                self.controller.logger.info(f"StateUpdater: {name} not registered, ignoring request")
                return
        else:
            entries_to_sync = self._registered_objects

        if not entries_to_sync:
            self.controller.logger.info("StateUpdater: No registered objects to sync, ignoring request")
            return

        for name, entry in list(entries_to_sync.items()):
            self.controller.logger.debug(f"StateUpdater: Syncing {name}")
            get_target_state_fun = entry["get"]
            set_state_fun = entry["set"]

            new_target_state = None

            try:
                new_target_state = await get_target_state_fun()
            except Exception as e:
                self.controller.logger.error(f"StateUpdater: Error syncing {name}: Failed to retrieve current state: {e}")

            try:
                await set_state_fun(new_target_state)
            except Exception as e:
                self.controller.logger.error(f"StateUpdater: Error syncing {name}: Failed to set state '{new_target_state}': {e}")

    def register(
        self,
        name: str,
        get_state: Callable[[], Awaitable[Any]],
        update_obj: Callable[[Any], Awaitable[None]],
    ):
        if self._registered_objects.get(name, None) is not None:
            self.controller.logger.info(f"StateUpdater: {name} already registered, overwriting existing entry")

        self._registered_objects[name] = {
            "name": name,
            "get": get_state,
            "set": update_obj,
        }

    def clear(self):
        self.controller.logger.info("StateUpdater: Clearing registry.")
        self._registered_objects = {}
