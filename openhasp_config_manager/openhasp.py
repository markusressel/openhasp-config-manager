import requests as requests

from openhasp_config_manager.model import Device

GET = "get"
POST = "post"


def upload_file(device: Device, name: str, content: str):
    url = device.webserver.website
    if not url.endswith("/"):
        url += "/"
    url += "edit"

    username = device.webserver.user
    password = device.webserver.password
    _do_request(
        POST, url,
        data={
            f"{name}": content
        },
        username=username, password=password
    )


def _do_request(method: str = GET, url: str = "/", params: dict = None,
                json: dict = None, data: any = None, headers: dict = None, username: str = None,
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
        response = requests.get(url, headers=_headers, json=json, files=data, auth=(username, password))
    elif method is POST:
        response = requests.post(url, headers=_headers, json=json, files=data, auth=(username, password))
    else:
        raise ValueError("Unsupported method: {}".format(method))

    response.raise_for_status()
    if len(response.content) > 0:
        if "application/json" in response.headers.get("Content-Type", ""):
            return response.json()
        else:
            return response.content
