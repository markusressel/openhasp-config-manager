from typing import Callable, Dict, Awaitable, Any, List, TYPE_CHECKING

from appdaemon import ADAPI

from openhasp_config_manager.ad.objects import ObjectController
from openhasp_config_manager.ad.objects.button import ButtonObjectController, SceneButtonObjectController
from openhasp_config_manager.ad.objects.image import ImageObjectController
from openhasp_config_manager.ad.objects.label import LabelObjectController
from openhasp_config_manager.ad.objects.progress import BarObjectController
from openhasp_config_manager.ad.objects.slider import SliderObjectController
from openhasp_config_manager.ad.objects.switch import SwitchObjectController

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page.state_updater import StateUpdater
    from openhasp_config_manager.ad.plate import PlateBehavior, PlateController
else:
    StateUpdater = Any
    PlateBehavior = Any


class PageController:
    """
    Controller for a single page on an OpenHASP plate.
    """

    def __init__(
        self,
        app: ADAPI,
        state_updater: StateUpdater,
        plate: "PlateController",
        index: int
    ):
        self.app = app
        self.index = index
        self.state_updater = state_updater
        self.plate = plate
        self.client = self.plate.client

        self.objects: Dict[int, ObjectController] = {}

    async def register_objects(self):
        raise NotImplementedError("register_objects must be implemented by subclass")

    async def initialize_objects(self):
        for ob in self.objects.values():
            await ob.init()

    async def request_plate_behavior(self, behavior: "PlateBehavior"):
        await self.plate.request_behavior(self, behavior)

    async def drop_plate_behavior(self, behavior: "PlateBehavior"):
        await self.plate.drop_behavior_request(self, behavior)

    async def has_plate_behavior(self, behavior: "PlateBehavior") -> bool:
        return self.plate.has_behavior_request(behavior)

    async def add_label(
        self,
        obj_id: int,
        entity_id: str | List[str] = None,
        attribute: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        text: Callable[[Any], str] = lambda x: str(x)
    ) -> LabelObjectController:
        """
        Adds a text object to the page.
        :param obj_id: the id of the object
        :param entity_id: (optional) the entity to bind to
        :param attribute: (optional) the attribute to bind to
        :param get_state: (optional) a function to get the current state
        :param text: a function that takes the state and returns a string
        :return: the text object controller
        """
        text = LabelObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            entity_id=entity_id,
            attribute=attribute,
            get_state=get_state,
            converter=text,
        )
        await self.add_object_controller(text)
        return text

    async def add_button(
        self,
        obj_id: int,
        on_click: Callable[[str, Dict], Awaitable[Any]],
    ) -> ButtonObjectController:
        """
        Adds a button object to the page.
        :param obj_id: the id of the object
        :param on_click: callable(topic, payload) to be called when the button is clicked
        :return: the button object controller
        """
        button = ButtonObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            on_click=on_click,
        )
        await self.add_object_controller(button)
        return button

    async def add_scene_button(
        self,
        obj_id: int,
        scene: str
    ) -> SceneButtonObjectController:
        """
        Adds a button object to the page that activates a scene.
        :param obj_id: the id of the object
        :param scene: the name of the scene to activate
        :return: the scene button object controller
        """
        button = SceneButtonObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            scene=scene,
        )
        await self.add_object_controller(button)
        return button

    async def add_switch(
        self,
        obj_id: int,
        entity_id: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
    ) -> SwitchObjectController:
        """
        Adds a switch object to the page.
        :param obj_id: the id of the object
        :param entity_id: (optional) the entity to bind to
        :param get_state: (optional) a function to get the current state of the switch
        :return: the switch object controller
        """
        switch: SwitchObjectController = SwitchObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            entity_id=entity_id,
            get_state=get_state,
        )
        await self.add_object_controller(switch)
        return switch

    async def add_slider(
        self,
        obj_id: int,
        entity_id: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        on_changed: Callable[[Any], Awaitable[None]] = None,
        on_released: Callable[[Any], Awaitable[None]] = None,
    ) -> SliderObjectController:
        """
        Adds a slider object to the page.
        :param obj_id: the id of the object
        :param entity_id: (optional) the entity to bind to
        :param get_state: (optional) a function to determine the current position of the slider
        :param on_changed: (optional) a function to call when the slider is changed by user input
        :param on_released: (optional) a function to call when the slider handle is released (user input ends)
        :return: the slider object controller
        """
        slider = SliderObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            entity_id=entity_id,
            get_state=get_state,
            on_changed=on_changed,
            on_released=on_released,
        )
        await self.add_object_controller(slider)
        return slider

    async def add_bar(
        self,
        obj_id: int,
        entity_id: str = None,
        get_state: Callable[[], Awaitable[Any]] = None,
        transform_value: Callable[[Any], int] = None,
    ) -> BarObjectController:
        """
        Adds a progress object to the page.
        :param obj_id: the id of the object
        :param entity_id: the entity to bind to
        :param get_state: a function to get the current state (if not using entity binding)
        :param transform_value: a function to transform the entity value to a progress value
        :return: the progress object controller
        """
        bar = BarObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
            entity_id=entity_id,
            get_state=get_state,
            transform_value=transform_value,
        )
        await self.add_object_controller(bar)
        return bar

    async def add_image(
        self,
        obj_id: int
    ) -> ImageObjectController:
        """
        Adds an image object to the page.
        :param obj_id: the id of the object
        :return: the image object controller
        """
        image = ImageObjectController(
            app=self.app,
            client=self.client,
            state_updater=self.state_updater,
            page=self.index,
            obj_id=obj_id,
        )
        await self.add_object_controller(image)
        return image

    async def add_object_controller(self, object_controller: ObjectController):
        """
        Adds an object controller to the page.
        :param object_controller:  the object controller to add
        """
        if object_controller.obj_id in self.objects:
            raise ValueError(f"Object with id {object_controller.obj_id} already exists on page {self.index}")
        self.objects[object_controller.obj_id] = object_controller

    async def go_to_this_page(self):
        """
        Changes the page to this page.
        """
        await self.plate.change_page(index=self.index)
