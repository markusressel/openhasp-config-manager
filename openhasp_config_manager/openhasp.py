import json
from typing import Dict, List

import requests as requests

from openhasp_config_manager.model import Device, MqttConfig, HttpConfig, GuiConfig, HaspConfig

GET = "GET"
POST = "POST"
DELETE = "DELETE"


class OpenHaspClient:

    def get_files(self, device: Device) -> List[str]:
        """
        Retrieve a list of all file on the device
        :param device: the device to query
        :return: a list of all files on the device
        """
        base_url = self._compute_base_url(device)

        username = device.config.http.user
        password = device.config.http.password

        response = self._do_request(
            GET,
            base_url + "list?dir=/",
            username=username, password=password
        )
        response_data = json.loads(response.decode('utf-8'))

        files = list(filter(lambda x: x["type"] == "file", response_data))
        file_names = list(map(lambda x: x["name"], files))
        return file_names

    def get_file_content(self, device: Device, file_name: str) -> str or None:
        base_url = self._compute_base_url(device)

        username = device.config.http.user
        password = device.config.http.password

        try:
            response = self._do_request(
                GET,
                base_url + file_name,
                username=username, password=password
            )
            response_data = response.decode('utf-8')
            return response_data
        except Exception as ex:
            return None

    def delete_file(self, device: Device, file_name: str):
        """
        Delete a file on the device
        :param device: the target device
        :param file_name: the name of the file
        """
        base_url = self._compute_base_url(device)

        username = device.config.http.user
        password = device.config.http.password

        self._do_request(
            DELETE,
            base_url + "edit",
            data={
                "path": "/" + file_name
            },
            username=username, password=password
        )

    def command(self, device: Device, name: str, params: str):
        """
        Execute a command on a device
        :param device: the device to request
        :param name: the name of the command
        :param params: parameters for the command
        """

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

        data = params.strip('"')
        result = client.publish(topic=topic, payload=data)
        result.wait_for_publish()

        if not result.rc == paho.MQTT_ERR_SUCCESS:
            print('Code %d while sending message %d: %s' % (result.rc, result.mid, paho.error_string(result.rc)))

    def reboot(self, device: Device):
        """
        Request a reboot
        :param device: the target device
        """
        base_url = self._compute_base_url(device)
        username = device.config.http.user
        password = device.config.http.password
        self._do_request(
            GET, base_url + "reboot",
            username=username, password=password
        )

    def set_hasp_config(self, device: Device, config: HaspConfig):
        """
        Set the "HASP" configuration
        :param device: the target device
        :param config: the configuration to set
        """
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
        """
        Set the HTTP configuration
        :param device: the target device
        :param config: the configuration to set
        """
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
        """
        Set the MQTT configuration
        :param device: the target device
        :param config: the configuration to set
        :return:
        """
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
        """
        Set the GUI configuration
        :param device: the target device
        :param config: the configuration to set
        :return:
        """
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
        """
        Upload a collection of files
        :param device: the target device
        :param files: "target file name"->"file content" mapping
        """
        for name, content in files.items():
            self.upload_file(device, name, content)

    def upload_file(self, device: Device, name: str, content: str):
        """
        Upload a single file
        :param device: the target device
        :param name: the target name of the file on the device
        :param content: the file content
        """
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

    @staticmethod
    def _compute_base_url(device: Device) -> str:
        url = device.config.openhasp_config_manager.device.ip
        if not url.startswith("http://"):
            url = "http://" + url
        if not url.endswith("/"):
            url += "/"
        return url
