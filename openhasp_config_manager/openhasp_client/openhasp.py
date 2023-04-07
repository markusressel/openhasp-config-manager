import json
from typing import Dict, List, Any, Callable

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from openhasp_config_manager.openhasp_client.telnet_client import OpenHaspTelnetClient
from openhasp_config_manager.openhasp_client.webservice_client import WebserviceClient
from openhasp_config_manager.ui.util import info


class OpenHaspClient:

    def __init__(self, device: Device):
        """
        :param device: the device this client can communicate with
        """
        self._device = device

        self._webservice_client = WebserviceClient(
            url=device.config.openhasp_config_manager.device.ip,
            username=self._device.config.http.user,
            password=self._device.config.http.password
        )

        self._mqtt_client = MqttClient(
            host=device.config.mqtt.host,
            port=device.config.mqtt.port,
            mqtt_user=device.config.mqtt.user,
            mqtt_password=device.config.mqtt.password
        )

        self._telnet_client = OpenHaspTelnetClient(
            host=device.config.openhasp_config_manager.device.ip,
            port=device.config.telnet.port,
            baudrate=device.config.debug.baud,
            user=device.config.http.user,
            password=device.config.http.password,
        )

    async def send_image(self, image: any, page: int, object_id: int):
        """
        Send an image to the device
        :param image: the image to send
        :param page: the page to send the image to
        :param object_id: the object id to send the image to
        """
        pass

    async def set_text(self, obj: str, text: str):
        """
        Set the text of an object
        :param obj: the object to set the text for
        :param text: the text to set
        """
        await self.set_object_properties(obj, {"text": text})

    async def set_object_properties(self, obj: str, properties: Dict[str, Any]):
        """
        Set the state of a plate
        :param obj: object to set a state for
        :param properties: properties to set
        """
        for prop, value in properties.items():
            await self.command(
                name=f"{obj}.{prop}",
                params=value,
            )

    async def set_idle_state(self, state: str):
        """
        Forces the given idle state
        :param state: one of "off", "short", "long"
        """
        return await self.command(
            name="idle",
            params=state
        )

    async def set_backlight(self, state: bool, brightness: int):
        """
        Sets the backlight state and brightness
        :param state: True to turn on, False to turn off
        :param brightness: the brightness level in 0..255
        """
        return await self.command(
            name="backlight",
            params=json.dumps({
                "state": state,
                "brightness": brightness,
            })
        )

    async def wakeup(self):
        """
        Wakes up the display
        """
        return await self.set_idle_state(state="off")

    async def set_page(self, index: int):
        """
        Set the current page
        :param index: the index of the page to set
        """
        return await self.command(
            name="page",
            params=f"{index}"
        )

    async def set_hidden(self, obj: str, hidden: bool):
        """
        Set the "hidden" property of an object
        :param obj: the object to set the property for
        :param hidden: True to hide the object, False to show it
        """
        return await self.set_object_properties(
            obj=obj,
            properties={
                "hidden": "1" if hidden else "0",
            }
        )

    async def listen_state(
            self,
            callback: Callable,
            state: str,
    ):
        """
        Listen to OpenHASP state events
        :param callback: callback to call when a matching event is received
        :param state: state to listen for
        :return: A handle that can be used to cancel the callback.
        """
        plate = self._device.config.mqtt.name

        async def _callback(event_topic: str, event_payload: bytes):
            event_topic_segments = event_topic.split('/')

            if len(event_topic_segments) != 4 or event_topic_segments[2] != "state":
                return

            event_plate = event_topic_segments[1]
            event_state_name = event_topic_segments[3]

            if (event_plate == plate) and event_state_name == state:
                await callback(event_topic, event_plate, event_state_name, event_payload)

        await self.listen_event(
            path=f"hasp/{plate}/state/{state}",
            callback=_callback,
        )

    async def listen_event(self, path: str, callback: Callable):
        """
        Listen for an event
        :param path:
        :param callback:
        :return:
        """

        async def _on_message(topic: str, payload: bytes):
            await callback(topic, payload)

        topic = f"hasp/{self._device.config.mqtt.name}/{path}"
        await self._mqtt_client.subscribe(topic, _on_message)

    async def command(self, name: str, params: str):
        """
        Execute a command on a device
        :param name: the name of the command
        :param params: parameters for the command
        """
        topic = f"hasp/{self._device.config.mqtt.name}/command/{name}"
        data = params.strip('"')
        await self._mqtt_client.publish(topic=topic, payload=data)

    def get_files(self) -> List[str]:
        """
        Retrieve a list of all file on the device
        :return: a list of all files on the device
        """
        return self._webservice_client.get_files()

    def get_file_content(self, file_name: str) -> str or None:
        return self._webservice_client.get_file_content(file_name)

    def delete_file(self, file_name: str):
        """
        Delete a file on the device
        :param file_name: the name of the file
        """
        self._webservice_client.delete_file(file_name)

    def reboot(self):
        """
        Request a reboot
        """
        self._webservice_client.reboot()

    def set_hasp_config(self, config: HaspConfig):
        """
        Set the "HASP" configuration
        :param config: the configuration to set
        """
        self._webservice_client.set_hasp_config(config)

    def set_http_config(self, config: HttpConfig):
        """
        Set the HTTP configuration
        :param config: the configuration to set
        """
        self._webservice_client.set_http_config(config)

    def get_mqtt_config(self) -> MqttConfig:
        return self._webservice_client.get_mqtt_config()

    def set_mqtt_config(self, config: MqttConfig):
        """
        Set the MQTT configuration
        :param config: the configuration to set
        :return:
        """
        self._webservice_client.set_mqtt_config(config)

    def set_gui_config(self, config: GuiConfig):
        """
        Set the GUI configuration
        :param config: the configuration to set
        :return:
        """
        self._webservice_client.set_gui_config(config)

    def upload_files(self, files: Dict[str, str]):
        """
        Upload a collection of files
        :param files: "target file name"->"file content" mapping
        """
        self._webservice_client.upload_files(files)

    def upload_file(self, name: str, content: str):
        """
        Upload a single file
        :param name: the target name of the file on the device
        :param content: the file content
        """
        info(f"Uploading '{name}'...")
        self._webservice_client.upload_file(name, content)

    def take_screenshot(self) -> bytes:
        """
        Requests a screenshot from the device.
        :return:
        """
        return self._webservice_client.take_screenshot()

    async def shell(self):
        await self._telnet_client.shell()

    async def logs(self):
        await self._telnet_client.logs()
