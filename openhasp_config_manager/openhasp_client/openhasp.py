from typing import Dict, List

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

    def watch(self):
        self._mqtt_client.watch(self._device)

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

    @staticmethod
    def _do_request(method: str = GET, url: str = "/", params: dict = None,
                    json: any = None, files: any = None, data: any = None,
                    headers: dict = None,
                    username: str = None, password: str = None) -> list or dict or None:
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
            json=json, files=files,
            data=data,
            auth=(username, password),
            timeout=5
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
