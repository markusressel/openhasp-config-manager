import json
from typing import Dict, List, Any, Callable, Union

import orjson
import requests as requests

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from openhasp_config_manager.ui.util import info

GET = "GET"
POST = "POST"
DELETE = "DELETE"


class OpenHaspClient:

    def __init__(self, device: Device):
        """
        :param device: the device this client can communicate with
        """
        self._device = device
        self._base_url = self._compute_base_url(self._device)

        self._mqtt_client = MqttClient(
            host=device.config.mqtt.host,
            port=device.config.mqtt.port,
            mqtt_user=device.config.mqtt.user,
            mqtt_password=device.config.mqtt.password
        )

    def send_image(self, image: any, page: int, object_id: int):
        """
        Send an image to the device
        :param image: the image to send
        :param page: the page to send the image to
        :param object_id: the object id to send the image to
        """
        pass

    def set_text(self, obj: str, text: str):
        """
        Set the text of an object
        :param obj: the object to set the text for
        :param text: the text to set
        """
        self.set_object_properties(obj, {"text": text})

    def set_object_properties(self, obj: str, properties: Dict[str, Any]):
        """
        Set the state of a plate
        :param obj: object to set a state for
        :param properties: properties to set
        """
        for prop, value in properties.items():
            self.command(
                name=f"{obj}.{prop}",
                params=value,
            )

    def set_idle_state(self, state: str):
        """
        Forces the given idle state
        :param state: one of "off", "short", "long"
        """
        return self.command(
            name="idle",
            params=state
        )

    def set_backlight(self, state: bool, brightness: int):
        """
        Sets the backlight state and brightness
        :param state: True to turn on, False to turn off
        :param brightness: the brightness level in 0..255
        """
        return self.command(
            name="backlight",
            params=json.dumps({
                "state": state,
                "brightness": brightness,
            })
        )

    def wakeup(self):
        """
        Wakes up the display
        """
        return self.set_idle_state(state="off")

    def set_page(self, index: int):
        """
        Set the current page
        :param index: the index of the page to set
        """
        return self.command(
            name="page",
            params=f"{index}"
        )

    def set_hidden(self, obj: str, hidden: bool):
        """
        Set the "hidden" property of an object
        :param obj: the object to set the property for
        :param hidden: True to hide the object, False to show it
        """
        return self.set_object_properties(
            obj=obj,
            properties={
                "hidden": "1" if hidden else "0",
            }
        )

    def get_files(self) -> List[str]:
        """
        Retrieve a list of all file on the device
        :return: a list of all files on the device
        """
        username = self._device.config.http.user
        password = self._device.config.http.password

        response = self._do_request(
            method=GET,
            url=self._base_url + "list?dir=/",
            username=username, password=password
        )
        response_data = orjson.loads(response.decode('utf-8'))

        files = list(filter(lambda x: x["type"] == "file", response_data))
        file_names = list(map(lambda x: x["name"], files))
        return file_names

    def get_file_content(self, file_name: str) -> str or None:
        username = self._device.config.http.user
        password = self._device.config.http.password

        try:
            response = self._do_request(
                method=GET,
                url=self._base_url + file_name,
                username=username, password=password
            )
            response_data = response.decode('utf-8')
            return response_data
        except Exception as ex:
            return None

    def delete_file(self, file_name: str):
        """
        Delete a file on the device
        :param file_name: the name of the file
        """
        username = self._device.config.http.user
        password = self._device.config.http.password

        self._do_request(
            method=DELETE,
            url=self._base_url + "edit",
            data={
                "path": "/" + file_name
            },
            username=username, password=password
        )

    def listen_state(
            self,
            callback: Callable,
            state: str,
            plate: str = "+",
    ) -> Union[str, list]:
        """
        Listen to OpenHASP state events
        :param callback: callback to call when a matching event is received
        :param plate: name of the plate
        :param state: state to listen for
        :return: A handle that can be used to cancel the callback.
        """

        async def _callback(event_topic, event_payload):
            event_topic_segments = event_topic.split('/')

            if len(event_topic_segments) != 4 or event_topic_segments[2] != "state":
                return

            event_plate = event_topic_segments[1]
            event_state_name = event_topic_segments[3]

            if (plate == "+" or event_plate == plate) and event_state_name == state:
                await callback(event_topic, event_plate, event_state_name, event_payload)

        self.listen_event(
            path=f"hasp/{plate}/state/{state}",
            callback=_callback,
        )

    def listen_event(self, path: str, callback: Callable):
        """
        Listen for an event
        :param path:
        :param callback:
        :return:
        """

        def _on_message(message: str):
            callback(message)

        topic = f"hasp/{self._device.config.mqtt.name}/{path}"
        self._mqtt_client.subscribe(topic, _on_message)

    def command(self, name: str, params: str):
        """
        Execute a command on a device
        :param name: the name of the command
        :param params: parameters for the command
        """
        topic = f"hasp/{self._device.config.mqtt.name}/command/{name}"
        data = params.strip('"')
        self._mqtt_client.publish(topic=topic, payload=data)

    def reboot(self):
        """
        Request a reboot
        """
        username = self._device.config.http.user
        password = self._device.config.http.password
        self._do_request(
            method=GET,
            url=self._base_url + "reboot",
            username=username, password=password
        )

    def set_hasp_config(self, config: HaspConfig):
        """
        Set the "HASP" configuration
        :param config: the configuration to set
        """
        data = {
            "startpage": config.startpage,
            "startdim": config.startdim,
            "theme": config.theme,
            "color1": config.color1,
            "color2": config.color2,
            "font": config.font,
            "pages": config.pages,
            "save": "hasp"
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        username = self._device.config.http.user
        password = self._device.config.http.password

        self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
            username=username, password=password
        )

    def set_http_config(self, config: HttpConfig):
        """
        Set the HTTP configuration
        :param config: the configuration to set
        """
        data = {
            "user": config.user,
            "pass": config.password,
            "save": "http"
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        username = self._device.config.http.user
        password = self._device.config.http.password

        self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
            username=username, password=password
        )

    def get_mqtt_config(self) -> MqttConfig:
        username = self._device.config.http.user
        password = self._device.config.http.password

        data = self._do_request(
            method=GET,
            url=self._base_url + "api/config/mqtt/",
            username=username, password=password
        )

        return MqttConfig(
            name=data["name"],
            group=data["group"],
            host=data["host"],
            port=data["port"],
            user=data["user"],
            password=data["pass"]
        )

    def set_mqtt_config(self, config: MqttConfig):
        """
        Set the MQTT configuration
        :param config: the configuration to set
        :return:
        """
        data = {
            "name": config.name,
            "group": config.group,
            "host": config.host,
            "port": config.port,
            "user": config.user,
            "pass": config.password,
            "save": "mqtt"
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        username = self._device.config.http.user
        password = self._device.config.http.password

        self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
            username=username, password=password
        )

    def set_gui_config(self, config: GuiConfig):
        """
        Set the GUI configuration
        :param config: the configuration to set
        :return:
        """
        data = {
            "idle1": config.idle1,
            "idle2": config.idle2,
            "rotate": config.rotate,
            "cursor": config.cursor,
            "bckl": config.bckl,
            "save": "gui"
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        username = self._device.config.http.user
        password = self._device.config.http.password

        self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
            username=username, password=password
        )

    def upload_files(self, files: Dict[str, str]):
        """
        Upload a collection of files
        :param files: "target file name"->"file content" mapping
        """
        for name, content in files.items():
            self.upload_file(name, content)

    def upload_file(self, name: str, content: str):
        """
        Upload a single file
        :param name: the target name of the file on the device
        :param content: the file content
        """
        info(f"Uploading '{name}'...")

        username = self._device.config.http.user
        password = self._device.config.http.password
        self._do_request(
            method=POST,
            url=self._base_url + "edit",
            files={
                f"{name}": content
            },
            username=username, password=password
        )

    def take_screenshot(self) -> bytes:
        """
        Requests a screenshot from the device.
        :return:
        """
        username = self._device.config.http.user
        password = self._device.config.http.password

        return self._do_request(
            method=GET,
            url=self._base_url + "screenshot",
            params={
                "q": "0"
            },
            stream=True,
            username=username, password=password
        )

    @staticmethod
    def _do_request(method: str = GET, url: str = "/", params: dict = None,
                    json: any = None, files: any = None, data: any = None,
                    headers: dict = None,
                    username: str = None, password: str = None,
                    stream: bool = None) -> list or dict or None:
        """
        Executes a http request based on the given parameters

        :param method: the method to use (GET, POST)
        :param url: the url to use
        :param params: query parameters that will be appended to the url
        :param json: request body
        :param headers: custom headers
        :return: the response parsed as a json
        """
        _headers = {
        }
        if headers is not None:
            _headers.update(headers)

        response = requests.request(
            method, url, headers=_headers,
            params=params,
            json=json, files=files,
            data=data,
            auth=(username, password),
            timeout=5,
            stream=stream,
        )

        response.raise_for_status()
        if len(response.content) > 0:
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            else:
                return response.content

    @staticmethod
    def _compute_base_url(device: Device) -> str:
        url = device.config.openhasp_config_manager.device.ip
        if not url.startswith("http://"):
            url = "http://" + url
        if not url.endswith("/"):
            url += "/"
        return url
