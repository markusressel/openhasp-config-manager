"""
A fake openHASP plate for the tests of `openhasp_config_manager.haad`.

The real `OpenHaspClient`, `MqttClient` and `WebserviceClient` are used; only their network layers (the `aiomqtt`
client and the HTTP request) are replaced. That way the topic and payload formatting of the client is part of what the
tests pin, and the fakes have the shape of the real thing.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import aiohttp
import orjson
from aiomqtt import Message

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.openhasp_client.webservice_client import WebserviceClient

_IMAGE_SOURCE = re.compile(r"^p\d+b\d+\.src=(http://\S+)$")


@dataclass(frozen=True)
class Mqtt:
    """A message the client published."""

    topic: str
    payload: Any


@dataclass(frozen=True)
class Http:
    """A request the client sent to the plate's web server (url relative to the plate's base url)."""

    method: str
    url: str
    data: Any = None


@dataclass
class FakePlate:
    """
    The device side of an openHASP plate (and the MQTT broker in between).

    - `traffic`: everything the client sent, over MQTT and HTTP, in order.
    - `send()`: a message from the plate (`LWT`, `state/idle`, `state/p1b2`, ...), delivered to the client's subscriptions.
    - `online`: while False, HTTP requests fail like for a plate that can't be reached.
    - Images: when an object's `src` is set to an http URL, the plate downloads it, like the real one.
    """

    mqtt_name: str = "mqtt_name"
    online: bool = True
    files: List[str] = field(default_factory=lambda: ["boot.cmd", "pages.jsonl"])
    traffic: List[Mqtt | Http] = field(default_factory=list)
    downloaded_images: List[bytes] = field(default_factory=list)
    _connections: List["_FakeAiomqttClient"] = field(default_factory=list)
    _downloads: List[asyncio.Task] = field(default_factory=list)

    @property
    def mqtt(self) -> List[Tuple[str, Any]]:
        """The published MQTT messages as (topic, payload), in order."""
        return [(m.topic, m.payload) for m in self.traffic if isinstance(m, Mqtt)]

    @property
    def commands(self) -> List[str]:
        """
        The commands sent to the plate, in order, in a compact form: `p1b2.text=abc` for `hasp/<name>/command` messages,
        `<keyword> <payload>` for `hasp/<name>/command/<keyword>` messages.
        """
        prefix = f"hasp/{self.mqtt_name}/command"
        result = []
        for topic, payload in self.mqtt:
            if not topic.startswith(prefix):
                raise AssertionError(f"Unexpected topic: {topic}")
            keyword = topic[len(prefix) + 1 :]
            result.append(f"{payload}" if not keyword else f"{keyword} {payload}")
        return result

    @property
    def http(self) -> List[Http]:
        return [m for m in self.traffic if isinstance(m, Http)]

    def clear(self):
        """Forgets the traffic so far, e.g. after the setup of a test."""
        self.traffic.clear()

    @property
    def subscribed(self) -> bool:
        """Whether the client is connected to the broker and listens to the plate's messages."""
        return len(self._connections) > 0

    async def send(self, path: str, payload: str | bytes | dict):
        """Publishes `hasp/<name>/<path>` from the plate."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        topic = f"hasp/{self.mqtt_name}/{path}"
        for connection in list(self._connections):
            await connection.queue.put(Message(topic, payload, qos=0, retain=False, mid=0, properties=None))
        await self.settle()

    async def settle(self):
        """
        Waits until the client handled every message sent so far and the plate downloaded every image. A message whose
        handler raised ends the connection (like in `MqttClient`), so it is not waited for.
        """
        for _ in range(10):
            await asyncio.sleep(0)
            for connection in self._connections:
                await connection.queue.join()
        while self._downloads:
            downloads, self._downloads = self._downloads, []
            await asyncio.gather(*downloads)

    def _published(self, topic: str, payload: Any):
        self.traffic.append(Mqtt(topic=topic, payload=payload))
        match = _IMAGE_SOURCE.match(str(payload))
        if match is not None:
            self._downloads.append(asyncio.ensure_future(self._download(match.group(1))))

    async def _download(self, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                self.downloaded_images.append(await response.read())

    def _request(self, method: str, url: str, data: Any) -> Any:
        if not self.online:
            raise aiohttp.ClientConnectionError(f"Plate offline: {method} {url}")
        self.traffic.append(Http(method=method, url=url, data=data))
        if url == "list?dir=/":
            return orjson.dumps([{"type": "file", "name": name} for name in self.files] + [{"type": "dir", "name": "dir"}])
        return None


class _FakeAiomqttClient:
    """The part of `aiomqtt.Client` that `MqttClient` uses."""

    def __init__(self, plate: FakePlate):
        self._plate = plate
        self.queue: asyncio.Queue[Message] = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self in self._plate._connections:
            self._plate._connections.remove(self)

    async def publish(self, topic: str, payload: Any = None):
        self._plate._published(topic, payload)

    async def subscribe(self, topic: str):
        assert topic == "hasp/#", topic
        self._plate._connections.append(self)

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        while True:
            message = await self.queue.get()
            yield message
            self.queue.task_done()


class FakeMqttClient(MqttClient):
    def __init__(self, plate: FakePlate, **kwargs):
        super().__init__(**kwargs)
        self._plate = plate

    def _create_mqtt_client(self):
        return _FakeAiomqttClient(self._plate)


class FakeWebserviceClient(WebserviceClient):
    def __init__(self, plate: FakePlate, **kwargs):
        super().__init__(**kwargs)
        self._plate = plate

    async def _do_request(self, method: str = "GET", url: str = "/", data: Any = None, **kwargs) -> Optional[Any]:
        assert url.startswith(self._base_url), url
        return self._plate._request(method, url[len(self._base_url) :], data)


class FakeOpenHaspClient(OpenHaspClient):
    """`OpenHaspClient` talking to a `FakePlate`."""

    def __init__(self, device: Device, plate: FakePlate):
        super().__init__(device)
        self._mqtt_client = FakeMqttClient(
            plate,
            host=device.config.mqtt.host,
            port=device.config.mqtt.port,
            mqtt_user=device.config.mqtt.user,
            mqtt_password=device.config.mqtt.password,
        )
        self._webservice_client = FakeWebserviceClient(
            plate,
            url=device.config.openhasp_config_manager.device.ip,
            username=device.config.http.user,
            password=device.config.http.password,
        )
