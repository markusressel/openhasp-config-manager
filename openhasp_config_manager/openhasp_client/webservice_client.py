from typing import Dict, List, Any, Optional

import aiohttp
import orjson

from openhasp_config_manager.openhasp_client.model.configuration.debug_config import DebugConfig
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.configuration.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.configuration.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.configuration.mqtt_config import MqttConfig, MqttTopicConfig
from openhasp_config_manager.openhasp_client.model.configuration.telnet_config import TelnetConfig

GET = "GET"
POST = "POST"
DELETE = "DELETE"

# how long a plate may take to answer a request, and how many bytes per second an upload is expected to reach at least
# (a 460 kB font took longer than 5 seconds)
REQUEST_TIMEOUT_SECONDS = 5
UPLOAD_BYTES_PER_SECOND = 20_000
# what the web server of the plate answers to a file it has stored
UPLOAD_OK_REPLY = "Upload OK"


class WebserviceClient:
    def __init__(self, url: str, username: str, password: str):
        self._username = username
        self._password = password
        self._base_url = self._compute_base_url(url)

    async def reboot(self):
        """
        Request a reboot
        """
        await self._do_request(
            method=GET,
            url=self._base_url + "reboot",
        )

    async def set_hasp_config(self, config: HaspConfig):
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
            "save": "hasp",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def get_http_config(self) -> HttpConfig:
        data = await self._do_request(
            method=GET,
            url=self._base_url + "api/config/http/",
        )

        return HttpConfig(
            port=data["port"],
            user=data["user"],
            password=data["pass"],
        )

    async def set_http_config(self, config: HttpConfig):
        """
        Set the HTTP configuration
        :param config: the configuration to set
        """
        data = {
            "user": config.user,
            "pass": config.password,
            "save": "http",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def get_mqtt_config(self) -> MqttConfig:
        data: Dict[str, Any] = await self._do_request(
            method=GET,
            url=self._base_url + "api/config/mqtt/",
        )

        return MqttConfig(
            name=data["name"],
            host=data["host"],
            port=data["port"],
            user=data["user"],
            password=data["pass"],
            topic=MqttTopicConfig(
                node=data["topic"]["node"],
                group=data["topic"]["group"],
                broadcast=data["topic"]["broadcast"],
                hass=data["topic"]["hass"],
            ),
        )

    async def set_mqtt_config(self, config: MqttConfig):
        """
        Set the MQTT configuration
        :param config: the configuration to set
        """
        data = {
            "name": config.name,
            "topic": {
                "node": config.topic.node,
                "group": config.topic.group,
                "broadcast": config.topic.broadcast,
                "hass": config.topic.hass,
            },
            "host": config.host,
            "port": config.port,
            "user": config.user,
            "pass": config.password,
            "save": "mqtt",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def get_gui_config(self) -> GuiConfig:
        data = await self._do_request(
            method=GET,
            url=self._base_url + "api/config/gui/",
        )

        return GuiConfig(
            idle1=data["idle1"],
            idle2=data["idle2"],
            rotate=data["rotate"],
            cursor=data["cursor"],
            bckl=data["bckl"],
            bcklinv=data["bcklinv"],
            invert=data["invert"],
            calibration=data["calibration"],
        )

    async def set_gui_config(self, config: GuiConfig):
        """
        Set the GUI configuration
        :param config: the configuration to set
        """
        data = {
            "idle1": config.idle1,
            "idle2": config.idle2,
            "rotate": config.rotate,
            "cursor": config.cursor,
            "bckl": config.bckl,
            "save": "gui",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def set_telnet_config(self, config: TelnetConfig):
        """
        Set the Debug configuration
        :param config: the configuration to set
        """
        data = {
            "enable": config.enable,
            "port": config.port,
            "save": "telnet",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def set_debug_config(self, config: DebugConfig):
        """
        Set the Debug configuration
        :param config: the configuration to set
        """
        data = {
            "ansi": config.ansi,
            "baud": config.baud,
            "tele": config.tele,
            "host": config.host,
            "port": config.port,
            "proto": config.proto,
            "log": config.log,
            "save": "debug",
        }

        # ignore keys with None value
        data = {k: v for k, v in data.items() if v is not None}

        await self._do_request(
            method=POST,
            url=self._base_url + "config",
            data=data,
        )

    async def upload_files(self, files: Dict[str, bytes]):
        """
        Upload a collection of files
        :param files: "target file name"->"file content" mapping
        """
        for name, content in files.items():
            await self.upload_file(name, content)

    async def upload_file(self, name: str, content: bytes):
        """
        Upload a single file
        :param name: the target name of the file on the device
        :param content: the file content
        """
        try:
            await self._do_request(
                method=POST,
                url=self._base_url + "edit",
                files={f"{name}": content},
            )
        except aiohttp.ClientResponseError as ex:
            # the web server of the plate sometimes sends a second status line after "Upload OK", which aiohttp rejects
            if UPLOAD_OK_REPLY not in ex.message:
                raise

    async def get_files(self) -> List[str]:
        """
        Retrieve a list of all file on the device
        :return: a list of all files on the device
        """
        response = await self._do_request(
            method=GET,
            url=self._base_url + "list?dir=/",
        )
        response_data = orjson.loads(response.decode("utf-8"))

        files = list(filter(lambda x: x["type"] == "file", response_data))
        file_names = list(map(lambda x: x["name"], files))
        return file_names

    async def get_file_content(self, file_name: str) -> Optional[bytes]:
        try:
            response = await self._do_request(
                method=GET,
                url=self._base_url + file_name,
            )
            response_data = response
            return response_data
        except Exception:
            return None

    async def delete_file(self, file_name: str):
        """
        Delete a file on the device
        :param file_name: the name of the file
        """
        await self._do_request(
            method=DELETE,
            url=self._base_url + "edit",
            data={"path": "/" + file_name},
        )

    async def take_screenshot(self) -> bytes:
        """
        Requests a screenshot from the device.
        :return:
        """
        return await self._do_request(
            method=GET,
            url=self._base_url + "screenshot",
            params={"q": "0"},
            stream=True,
        )

    async def _do_request(
        self,
        method: str = GET,
        url: str = "/",
        params: dict = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        headers: Dict = None,
        stream: bool = None,
    ) -> Optional[List | Dict | bytes]:
        _headers = {}
        if headers is not None:
            _headers.update(headers)

        if files:
            # simple multipart form data
            form = aiohttp.FormData()
            for k, v in files.items():
                form.add_field(k, v, filename=k)
            data = form

        auth = aiohttp.BasicAuth(self._username, self._password)
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=_headers,
                params=params,
                json=json,
                data=data,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds(files)),
            ) as response:
                response.raise_for_status()
                content = await response.read()
                if len(content) > 0:
                    if "application/json" in response.headers.get("Content-Type", ""):
                        return orjson.loads(content)
                    else:
                        return content
                return None

    @staticmethod
    def _timeout_seconds(files: Optional[Dict[str, bytes]]) -> float:
        """:return: how long a request may take: more for the upload of big files, which the plate writes to flash"""
        return REQUEST_TIMEOUT_SECONDS + sum(len(content) for content in (files or {}).values()) / UPLOAD_BYTES_PER_SECOND

    @staticmethod
    def _compute_base_url(url: str) -> str:
        if not url.startswith("http://"):
            url = "http://" + url
        if not url.endswith("/"):
            url += "/"
        return url
