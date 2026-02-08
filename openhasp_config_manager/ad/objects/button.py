from enum import StrEnum
from typing import Dict, Callable, Awaitable, Any, TYPE_CHECKING

from appdaemon import ADAPI

from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.ad.page import StateUpdater
else:
    StateUpdater = Any

from openhasp_config_manager.ad.objects import ObjectController


class ButtonEvent(StrEnum):
    UP = "up"


class ButtonObjectController(ObjectController):

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        on_click: Callable[[str, Dict], Awaitable[Any]],
    ):
        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id)
        self.on_click = on_click

    async def init(self):
        self.app.log(f"Initializing button object {self.object_id}", level="DEBUG")

        async def _click_callback(topic, payload: Dict):
            if payload["event"] == ButtonEvent.UP:
                await self._on_click(topic, payload)

        return await self.listen_obj(
            callback=_click_callback,
        )

    async def _on_click(self, topic: str, payload: Dict):
        await self.on_click(topic, payload)

    async def set_is_toggle(self, is_toggle: bool):
        """
        Sets whether this button object is a toggle button
        :param is_toggle: True if this is a "toggle-on/toggle-off" button, False for a normal button.
        """
        await self.set_object_properties(
            properties={
                "toggle": is_toggle,
            }
        )

    async def set_is_toggled(self, is_toggled: bool):
        """
        Sets whether this button object is toggled on or off
        :param is_toggled: True if this button object is toggled on, False if it is toggled off.
        """
        await self.set_object_properties(
            properties={
                "val": 1 if is_toggled else 0,
            }
        )

    async def set_text(self, text: str):
        """
        Sets the text for this button object
        :param text: the text to set
        """
        await self.set_object_properties(
            properties={
                "text": text,
            }
        )

    async def set_text_align(self, align: str):
        """
        Sets the text alignment for this button object
        :param align: the text alignment to set, one of "left", "center", "right"
        """
        await self.set_object_properties(
            properties={
                "align": align,
            }
        )


class SceneButtonObjectController(ButtonObjectController):
    SCENE_ENTITY_PREFIX = "scene."

    def __init__(
        self,
        app: ADAPI,
        client: OpenHaspClient,
        state_updater: StateUpdater,
        page: int,
        obj_id: int,
        scene: str,
    ):
        """
        Sets up a button to activate a scene
        :param scene: the name of the scene to activate
        """

        async def __on_click(topic: str, payload: Dict):
            await _activate_scene(controller=self.app, name=self.scene)

        super().__init__(app=app, client=client, state_updater=state_updater, page=page, obj_id=obj_id, on_click=__on_click)
        self.scene = scene

        async def _activate_scene(controller: ADAPI, name: str) -> Any:
            """
            Activate a scene
            :param controller: the ADAPI controller to use to call the service
            :param name: the scene to activate
            """
            scene_entity = name
            if not scene_entity.startswith(self.SCENE_ENTITY_PREFIX):
                scene_entity = f"{self.SCENE_ENTITY_PREFIX}{scene_entity}"
            controller.log(f"Activating scene {scene_entity}")
            return await controller.call_service(
                "scene/turn_on",
                entity_id=scene_entity
            )
