from typing import Dict

import requests as requests

from openhasp_config_manager.model import Device

GET = "get"
POST = "post"


class OpenHaspClient:

    def command(self, device: Device, name: str, params: str):
        pass

    def upload_files(self, device: Device, files: Dict[str, str]):
        for name, content in files.items():
            self.upload_file(device, name, content)

    def upload_file(self, device: Device, name: str, content: str):
        print(f"Uploading '{name}'...")

        url = device.webserver.website
        if not url.endswith("/"):
            url += "/"
        url += "edit"

        username = device.webserver.user
        password = device.webserver.password
        self._do_request(
            POST, url,
            files={
                f"{name}": content
            },
            username=username, password=password
        )

    @staticmethod
    def _do_request(method: str = GET, url: str = "/", params: dict = None,
                    json: dict = None, files: any = None, headers: dict = None, username: str = None,
                    password: str = None) -> list or dict or None:
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

        if method is GET:
            response = requests.get(url, headers=_headers, json=json, files=files, auth=(username, password), timeout=5)
        elif method is POST:
            response = requests.post(url, headers=_headers, json=json, files=files, auth=(username, password),
                                     timeout=30)
        else:
            raise ValueError("Unsupported method: {}".format(method))

        response.raise_for_status()
        if len(response.content) > 0:
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            else:
                return response.content
