from typing import Dict, Callable, Awaitable, Any, List, Mapping, Optional, TYPE_CHECKING

from haad.controller import HaadController
from haad.triggers.resolver import TriggerInput
from openhasp_config_manager.haad import STATE_UNKNOWN, STATE_UNAVAILABLE
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.haad.page.state_updater import StateUpdater


class ObjectController:
    """
    Base class for controllers for objects on the OpenHASP plate.
    This should be subclassed for each type of object to implement specific functionality for that object type.

    An object is either *external* (its layout is on the plate's flash, deployed from JSONL) or *owned* (it has a `rect`:
    haad pushes it to the plate).
    """

    # the openHASP object type ("obj" in JSONL)
    OBJ_TYPE: str = "obj"

    def __init__(
        self,
        controller: HaadController,
        client: OpenHaspClient,
        state_updater: "StateUpdater",
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

        # set by PageController.add_object_controller()
        self.rect: Optional[Rect] = None
        self.props: Mapping[str, Any] = {}
        self.parent: Optional["ObjectController"] = None
        # the layout node this object was mounted from, if any: a bound `hidden` collapses it
        self.layout_node = None
        self.trigger: Optional[TriggerInput] = None
        # where the object was declared, for the layout dumps
        self.declaration: Optional[str] = None
        # the rendered JSONL object, set when the plate renders its layout (owned objects only)
        self.jsonl: Dict[str, Any] = {}
        # whether the object exists on the plate: external objects always, owned ones once their page was pushed
        self.live = False
        self._sync_names: List[str] = []
        # what bind() and init() registered, for unbind()
        self._reactions: List[Any] = []
        self._listeners: List[Any] = []

    @property
    def obj_type(self) -> str:
        return self.OBJ_TYPE

    @property
    def owned(self) -> bool:
        """Whether haad owns this object, i.e. pushes it to the plate (it has a rect), instead of the plate's flash."""
        return self.rect is not None

    @property
    def deferred(self) -> bool:
        """
        Whether property changes are deferred: until its page is pushed, an owned object doesn't exist on the plate (and
        the push clears the page), so changes go into its `props`, and with them into the pushed JSONL.
        """
        return self.owned and not self.live

    async def send_properties(self, properties: Dict[str, Any]):
        """Sends properties to the plate, without de-duplication (see set_object_properties())."""
        if self.deferred:
            self.props = {**self.props, **properties}
            return
        await self.client.set_object_properties(obj=self.object_id, properties=properties)

    @property
    def static_props(self) -> Dict[str, Any]:
        return {k: v for k, v in self.props.items() if not isinstance(v, Bound)}

    @property
    def bound_props(self) -> Dict[str, Bound]:
        return {k: v for k, v in self.props.items() if isinstance(v, Bound)}

    async def react_to(self, **kwargs):
        """`HaadController.react_to()`, remembering the reaction so unbind() can cancel it."""
        handle = await self.controller.react_to(**kwargs)
        self._reactions.append(handle)
        return handle

    async def unbind(self):
        """Cancels everything init() and bind() registered: reactions, event listeners and StateUpdater entries."""
        reactions, self._reactions = self._reactions, []
        for handle in reactions:
            await self.controller.cancel_reaction(handle)
        listeners, self._listeners = self._listeners, []
        for listener in listeners:
            listener.cancel()
        names, self._sync_names = self._sync_names, []
        for name in names:
            self.state_updater.unregister(name)

    def register_state(self, name: str, get_state: Callable[[], Awaitable[Any]], update_obj: Callable[[Any], Awaitable[None]]):
        """Registers a StateUpdater entry of this object, see refresh()."""
        self.state_updater.register(name=name, get_state=get_state, update_obj=update_obj)
        self._sync_names.append(name)

    async def refresh(self):
        """Syncs the StateUpdater entries of this object (e.g. when its `trigger` fires)."""
        for name in self._sync_names:
            await self.state_updater.sync(name)

    async def bind(self):
        """
        Binds what every object type supports, after init(): `trigger` (refreshes the object), the static properties of
        external objects (set now and on every sync; owned objects get them with the pushed JSONL), and bound properties.
        """
        if self.trigger is not None:
            await self.react_to(trigger=self.trigger, action=self.refresh)

        static_props = self.static_props
        if static_props and not self.owned:
            name = f"props:{self.object_id}"

            async def _get_props():
                return static_props

            self.register_state(name=name, get_state=_get_props, update_obj=self.set_object_properties)
            await self.state_updater.sync(name)

        for key, bound in self.bound_props.items():
            await self._bind_property(key, bound)

    async def _bind_property(self, key: str, bound: Bound):
        name = f"bound:{self.object_id}:{key}"

        async def _get_value():
            if bound.get_state is not None:
                return await bound.get_state()
            state = await self.controller.ha.get_state(bound.entity_id)
            return None if state in [STATE_UNKNOWN, STATE_UNAVAILABLE] else state

        async def _set_value(value: Any):
            if bound.convert is not None:
                value = bound.convert(value)
            await self.set_object_properties(properties={key: value})
            if key == "hidden" and self.layout_node is not None:
                await self.layout_node.set_collapsed(value not in (None, 0, False, "0", ""))

        self.register_state(name=name, get_state=_get_value, update_obj=_set_value)

        async def _on_trigger():
            await self.state_updater.sync(name)

        await self.react_to(trigger=bound.entity_id or bound.trigger, action=_on_trigger, immediately=True)

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
        return await self.send_properties({"hidden": "1" if hidden else "0"})

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
        if self.deferred:
            return await self.send_properties(properties)

        changed_properties = {}
        for k, v in properties.items():
            if force or k not in self._last_properties or self._last_properties[k] != v:
                changed_properties[k] = v

        if not changed_properties:
            return

        for k, v in changed_properties.items():
            self._last_properties[k] = v

        self.controller.logger.debug(f"Setting properties of {self.object_id}: {changed_properties}")
        return await self.send_properties(changed_properties)

    async def listen_obj(self, callback: Callable[[str, Dict], Awaitable[Any]]):
        """
        Listens to events for the given object on the given page and calls the callback with it
        :param callback: the callback to call when an event for the given object is received
        """
        from openhasp_config_manager.haad import util_openhasp

        listener = await util_openhasp.listen_state(
            controller=self.controller,
            client=self.client,
            obj=self.object_id,
            callback=callback,
        )
        self._listeners.append(listener)
        return listener
