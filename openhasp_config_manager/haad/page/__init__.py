import os
import sys
from typing import Callable, Dict, Awaitable, Any, List, Mapping, Optional, Sequence, TYPE_CHECKING

from haad.controller import HaadController
from haad.hass.entity import HAEntity
from haad.triggers.resolver import TriggerInput
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.objects.button import ButtonObjectController, SceneButtonObjectController
from openhasp_config_manager.haad.objects.generic import GenericObjectController
from openhasp_config_manager.haad.objects.image import ImageObjectController
from openhasp_config_manager.haad.objects.label import LabelObjectController
from openhasp_config_manager.haad.objects.progress import BarObjectController
from openhasp_config_manager.haad.objects.slider import SliderObjectController
from openhasp_config_manager.haad.objects.switch import SwitchObjectController

if TYPE_CHECKING:
    from openhasp_config_manager.haad.layout.components import Page
    from openhasp_config_manager.haad.page.state_updater import StateUpdater
    from openhasp_config_manager.haad.plate import PlateController
    from openhasp_config_manager.haad.plate.scheduler import Claim, Priority
else:
    StateUpdater = Any

type EntityRef = HAEntity | str
"""An entity: its `HAEntity` wrapper or its entity id."""

type Props = Mapping[str, Any | Bound]
"""openHASP properties of an object: values, or `Bound` values that follow an entity."""

# the highest object id openHASP accepts
MAX_OBJ_ID = 254


def entity_ids(entity: EntityRef | Sequence[EntityRef] | None) -> str | List[str] | None:
    """The entity id(s) of `entity=` arguments: one id for one entity, a list for a list."""
    if entity is None:
        return None
    if isinstance(entity, (str, HAEntity)):
        return entity if isinstance(entity, str) else entity.entity_id
    return [entity_ids(e) for e in entity]


class PageController:
    """
    Controller for a single page on an OpenHASP plate.

    A page declares its objects in build_layout() (a component tree) and/or register_objects() (add_* calls). Every
    object is either external (its layout is on the plate's flash: give its `obj_id`) or owned (give its `rect`: haad
    pushes it to the plate). All objects of one page are either owned or external.
    """

    def __init__(
        self,
        controller: HaadController,
        state_updater: StateUpdater,
        plate: "PlateController",
        index: int,
    ):
        self.controller = controller
        self.index = index
        self.state_updater = state_updater
        self.plate = plate
        self.client = self.plate.client

        self.objects: Dict[int, ObjectController] = {}
        # ids that are taken by explicit obj_ids of the page's layout tree, before its objects are added
        self._reserved_ids: set[int] = set()

    async def build_layout(self) -> Optional["Page"]:
        """
        Declares the page's objects as a component tree, owned or (with Page(external=True)) external. It runs before
        register_objects(), which can use the `.obj` handles of the tree's leaves. Default: None.
        """
        return None

    async def register_objects(self):
        """
        Declares the page's objects with the add_* methods, and its behaviour (react_to(), plate behaviours, ...).
        Default: nothing.
        """

    async def initialize_objects(self):
        for ob in self.objects.values():
            await ob.init()
            await ob.bind()

    @property
    def owned(self) -> bool:
        """Whether haad owns this page's layout (its objects are owned), and pushes it to the plate."""
        return any(o.owned for o in self.objects.values())

    async def claim(
        self,
        active: Callable[[], Awaitable[bool]],
        trigger: TriggerInput,
        priority: "Priority" = None,
        keep_awake: bool = False,
        wake: bool = False,
    ) -> "Claim":
        """
        Claims the plate while `active()` is true, evaluated now and whenever `trigger` fires: the plate shows this page
        (see PageScheduler for how claims are arbitrated) and, with `keep_awake`, stays on. Call it in register_objects().

        :param priority: default: Priority.NORMAL
        :param wake: wakes the screen when the claim shows this page
        """
        from openhasp_config_manager.haad.plate.scheduler import Priority
        return await self.plate.scheduler.register(
            page=self, active=active, trigger=trigger, priority=priority or Priority.NORMAL, keep_awake=keep_awake, wake=wake
        )

    async def add_label(
        self,
        obj_id: int = None,
        entity: EntityRef | Sequence[EntityRef] = None,
        attribute: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        text: str | Callable[[Any], str] = lambda x: str(x),
        trigger: TriggerInput = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> LabelObjectController:
        """
        Adds a text object to the page.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param entity: (optional) the entity (or entities) to bind to, as HAEntity or entity id
        :param attribute: (optional) the attribute to bind to
        :param get_state: (optional) a function to get the current state
        :param text: a static text, or a function that takes the state and returns the text
        :param trigger: (optional) refreshes the text (from get_state) whenever it fires, e.g. Trigger.Time.every(...)
        :param rect: the object's position and size, relative to its parent: the object is owned, haad pushes it to the plate
        :param props: openHASP properties (values or Bound); fonts and images they reference must be on the plate's flash
        :param parent: the owned object this object is placed in (openHASP `parentid`)
        :return: the text object controller
        """
        props = dict(props or {})
        if isinstance(text, str):
            props.setdefault("text", text)
            static_text = text
            text = lambda x: static_text  # noqa: E731
        label = LabelObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            entity_id=entity_ids(entity),
            attribute=attribute,
            get_state=get_state,
            converter=text,
        )
        await self.add_object_controller(label, rect=rect, props=props, parent=parent, trigger=trigger)
        return label

    async def add_button(
        self,
        obj_id: int = None,
        on_click: Callable[[], Awaitable[Any]] = None,
        text: str = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> ButtonObjectController:
        """
        Adds a button object to the page.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param on_click: (optional) called when the button is clicked; without it, the button is a styled box
        :param text: (optional) the static text of the button
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the button object controller
        """
        button = ButtonObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            on_click=on_click,
        )
        await self.add_object_controller(button, rect=rect, props=_with_text(props, text), parent=parent)
        return button

    async def add_scene_button(
        self,
        obj_id: int = None,
        scene: str = None,
        text: str = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> SceneButtonObjectController:
        """
        Adds a button object to the page that activates a scene.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param scene: the name of the scene to activate
        :param text: (optional) the static text of the button
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the scene button object controller
        """
        if scene is None:
            raise ValueError("A scene button needs a scene")
        button = SceneButtonObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            scene=scene,
        )
        await self.add_object_controller(button, rect=rect, props=_with_text(props, text), parent=parent)
        return button

    async def add_switch(
        self,
        obj_id: int = None,
        entity: EntityRef | Sequence[EntityRef] = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        trigger: TriggerInput = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> SwitchObjectController:
        """
        Adds a switch object to the page.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param entity: (optional) the entity to bind to, as HAEntity or entity id
        :param get_state: (optional) a function to get the current state of the switch
        :param trigger: (optional) refreshes the switch (from get_state) whenever it fires
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the switch object controller
        """
        switch: SwitchObjectController = SwitchObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            entity_id=entity_ids(entity),
            get_state=get_state,
        )
        await self.add_object_controller(switch, rect=rect, props=props, parent=parent, trigger=trigger)
        return switch

    async def add_slider(
        self,
        obj_id: int = None,
        entity: EntityRef | Sequence[EntityRef] = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        on_changed: Callable[[Any], Awaitable[None]] = None,
        on_released: Callable[[Any], Awaitable[None]] = None,
        trigger: TriggerInput = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> SliderObjectController:
        """
        Adds a slider object to the page.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param entity: (optional) the entity to bind to, as HAEntity or entity id
        :param get_state: (optional) a function to determine the current position of the slider
        :param on_changed: (optional) a function to call when the slider is changed by user input
        :param on_released: (optional) a function to call when the slider handle is released (user input ends)
        :param trigger: (optional) refreshes the slider (from get_state) whenever it fires
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the slider object controller
        """
        slider = SliderObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            entity_id=entity_ids(entity),
            get_state=get_state,
            on_changed=on_changed,
            on_released=on_released,
        )
        await self.add_object_controller(slider, rect=rect, props=props, parent=parent, trigger=trigger)
        return slider

    async def add_bar(
        self,
        obj_id: int = None,
        entity: EntityRef | Sequence[EntityRef] = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        transform_value: Callable[[Any], int] = None,
        trigger: TriggerInput = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> BarObjectController:
        """
        Adds a progress object to the page.
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param entity: the entity to bind to, as HAEntity or entity id
        :param get_state: a function to get the current state (if not using entity binding)
        :param transform_value: a function to transform the entity value to a progress value
        :param trigger: (optional) refreshes the bar (from get_state) whenever it fires
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the progress object controller
        """
        bar = BarObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            entity_id=entity_ids(entity),
            get_state=get_state,
            transform_value=transform_value,
        )
        await self.add_object_controller(bar, rect=rect, props=props, parent=parent, trigger=trigger)
        return bar

    async def add_image(
        self,
        obj_id: int = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> ImageObjectController:
        """
        Adds an image object to the page. Images referenced from the plate's flash (`props={"src": "L:/..."}`) must be on
        the flash already: haad does not upload them. Images from URLs are pushed with push_image().
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the image object controller
        """
        image = ImageObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
        )
        await self.add_object_controller(image, rect=rect, props=props, parent=parent)
        return image

    async def add_object(
        self,
        obj: str,
        obj_id: int = None,
        *,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
    ) -> GenericObjectController:
        """
        Adds an object of any openHASP type without a dedicated add_* method (`obj`, `arc`, `line`, `roller`, ...). Fonts and
        images its properties reference must be on the plate's flash: haad does not upload them.
        :param obj: the openHASP object type
        :param obj_id: the id of the object; optional for owned objects (with `rect`)
        :param rect: see add_label()
        :param props: see add_label()
        :param parent: see add_label()
        :return: the object controller
        """
        generic = GenericObjectController(
            controller=self.controller,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=self._object_id(obj_id, rect),
            obj_type=obj,
        )
        await self.add_object_controller(generic, rect=rect, props=props, parent=parent)
        return generic

    def reserve_ids(self, ids: Sequence[int]):
        """Keeps these ids free for objects declared later with explicit ids (e.g. leaves of the layout tree)."""
        self._reserved_ids.update(ids)

    def _object_id(self, obj_id: Optional[int], rect: Optional[Rect]) -> int:
        """
        The id of a new object: the explicit one, or, for owned objects, the lowest free one (ids are allocated in
        declaration order; explicit and reserved ids are skipped).
        """
        if obj_id is not None:
            return obj_id
        if rect is None:
            raise ValueError(f"An object on page {self.index} needs an obj_id (external object) or a rect (owned object)")
        taken = set(self.objects) | self._reserved_ids
        for candidate in range(1, MAX_OBJ_ID + 1):
            if candidate not in taken:
                return candidate
        raise ValueError(f"Page {self.index} has more than {MAX_OBJ_ID} objects")

    async def add_object_controller(
        self,
        object_controller: ObjectController,
        rect: Rect = None,
        props: Props = None,
        parent: ObjectController = None,
        trigger: TriggerInput = None,
    ):
        """
        Adds an object controller to the page.
        :param object_controller:  the object controller to add
        :param rect: the object's rect, if it is owned
        :param props: its openHASP properties
        :param parent: the owned object it is placed in
        :param trigger: refreshes the object whenever it fires
        """
        if object_controller.obj_id in self.objects:
            raise ValueError(f"Object with id {object_controller.obj_id} already exists on page {self.index}")
        if parent is not None and (rect is None or not parent.owned):
            raise ValueError(f"Object {object_controller.object_id}: only owned objects can be placed in an owned parent")
        object_controller.rect = rect
        object_controller.props = dict(props or {})
        object_controller.parent = parent
        object_controller.trigger = trigger
        object_controller.declaration = object_controller.declaration or _declaration_site()
        self.objects[object_controller.obj_id] = object_controller

    async def go_to_this_page(self):
        """
        Changes the page to this page.
        """
        await self.plate.change_page(index=self.index)


def _with_text(props: Optional[Props], text: Optional[str]) -> Dict[str, Any]:
    props = dict(props or {})
    if text is not None:
        props.setdefault("text", text)
    return props


def _declaration_site() -> str:
    """`file.py:line` of the first caller outside this package, for the layout dumps."""
    frame = sys._getframe(1)
    while "openhasp_config_manager/haad/" in frame.f_code.co_filename:
        frame = frame.f_back
    return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno}"
