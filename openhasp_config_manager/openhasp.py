import json
from typing import Dict

import requests as requests

from openhasp_config_manager.model import Device, MqttConfig, HttpConfig, GuiConfig, HaspConfig

GET = "GET"
POST = "POST"


class OpenHaspClient:

    def command(self, device: Device, name: str, params: dict):

        import paho.mqtt.client as paho

        mqtt_host = device.config.mqtt.host
        mqtt_port = device.config.mqtt.port
        mqtt_client_id = 'openhasp-config-manager'
        mqtt_user = device.config.mqtt.user
        mqtt_password = device.config.mqtt.password

        topic = f"hasp/{device.config.mqtt.name}/command"

        client = paho.Client(client_id=mqtt_client_id, protocol=paho.MQTTv5)

        client.username_pw_set(username=mqtt_user, password=mqtt_password)
        client.connect(mqtt_host, mqtt_port)

        json_data = json.dumps(params).strip('"')

        data = " ".join([name, json_data])
        result = client.publish(topic=topic, payload=data)
        result.wait_for_publish()

        if not result.rc == paho.MQTT_ERR_SUCCESS:
            print('Code %d while sending message %d: %s' % (result.rc, result.mid, paho.error_string(result.rc)))

    def reboot(self, device: Device):
        base_url = self._compute_base_url(device)
        username = device.config.http.user
        password = device.config.http.password
        self._do_request(
            GET, base_url + "reboot",
            username=username, password=password
        )

    def set_hasp_config(self, device: Device, config: HaspConfig):
        base_url = self._compute_base_url(device)

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

        username = device.config.http.user
        password = device.config.http.password

        self._do_request(
            POST, base_url + "config",
            data=data,
            username=username, password=password
        )

    def set_http_config(self, device: Device, config: HttpConfig):
        base_url = self._compute_base_url(device)

        data = {
            "user": config.user,
            "pass": config.password,
            "save": "http"
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        username = device.config.http.user
        password = device.config.http.password

        self._do_request(
            POST, base_url + "config",
            data=data,
            username=username, password=password
        )

    def set_mqtt_config(self, device: Device, config: MqttConfig):
        base_url = self._compute_base_url(device)

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

        username = device.config.http.user
        password = device.config.http.password

        self._do_request(
            POST, base_url + "config",
            data=data,
            username=username, password=password
        )

    def set_gui_config(self, device: Device, config: GuiConfig):
        base_url = self._compute_base_url(device)

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

        username = device.config.http.user
        password = device.config.http.password

        self._do_request(
            POST, base_url + "config",
            data=data,
            username=username, password=password
        )

    def upload_files(self, device: Device, files: Dict[str, str]):
        for name, content in files.items():
            self.upload_file(device, name, content)

    def upload_file(self, device: Device, name: str, content: str):
        print(f"Uploading '{name}'...")

        url = self._compute_base_url(device)
        url += "edit"

        username = device.config.http.user
        password = device.config.http.password
        self._do_request(
            POST, url,
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

    def _compute_base_url(self, device: Device) -> str:
        url = device.config.openhasp_config_manager.device.ip
        if not url.startswith("http://"):
            url = "http://" + url
        if not url.endswith("/"):
            url += "/"
        return url
