import asyncio
import json
import uuid
from typing import Callable, List, Dict

from aiomqtt import Client, Message


class MqttClient:

    def __init__(self, host: str, port: int, mqtt_user: str, mqtt_password: str):
        self._mqtt_client_id = 'openhasp-config-manager'
        self._host = host
        self._port = port
        self._mqtt_user = mqtt_user
        self._mqtt_password = mqtt_password
        self._reconnect_interval_seconds = 5

        self._mqtt_client_task: asyncio.Task | None = None
        self._callbacks: Dict[str, List[callable]] = {}
        self.__mqtt_client: Client | None = None

    async def publish(self, topic: str, payload: any):
        """
        Publish a message to a topic
        :param topic: topic to publish to
        :param payload: payload to publish
        """
        async with self._create_mqtt_client() as client:
            if isinstance(payload, dict) or isinstance(payload, list):
                payload = json.dumps(payload)

            await client.publish(topic, payload=payload)

    async def subscribe(self, topic: str, callback: Callable):
        """
        Subscribe to a topic and call the callback when a message is received
        :param topic: topic to subscribe to
        :param callback: function to call when a message is received
        """
        if topic not in self._callbacks:
            self._callbacks[topic] = []
        if callback not in self._callbacks[topic]:
            self._callbacks[topic].append(callback)

        if self._mqtt_client_task is None:
            await self._start_mqtt_client_task()

    async def cancel_callback(self, topic: str = None, callback: Callable = None):
        """
        Cancel a single subscription callback or all callbacks for a specific topic
        :param topic: the topic to cancel all callbacks for
        :param callback: the specific callback to cancel
        """
        if topic is None and callback is None:
            raise ValueError('Must specify either topic, callback or both')

        if topic is not None and callback is not None:
            self._callbacks[topic] = list(filter(lambda x: x != callback, self._callbacks[topic]))

        elif topic is not None and topic in self._callbacks:
            self._callbacks.pop(topic)
        else:
            for topic in self._callbacks.keys():
                self._callbacks[topic] = list(filter(lambda x: x != callback, self._callbacks[topic]))

        if not any(self._callbacks.values()):
            await self._stop_mqtt_client_task()

    def _create_mqtt_client(self) -> Client:
        return Client(
            hostname=self._host,
            port=self._port,
            username=self._mqtt_user,
            password=self._mqtt_password,
            identifier=f"{self._mqtt_client_id}-{uuid.uuid4()}",
        )

    async def _start_mqtt_client_task(self):
        self._mqtt_client_task = asyncio.ensure_future(self._mqtt_client_task_function())

    async def _stop_mqtt_client_task(self):
        if self._mqtt_client_task is not None:
            self._mqtt_client_task.cancel()
            self._mqtt_client_task = None

    async def _mqtt_client_task_function(self):
        while True:
            try:
                async with self._create_mqtt_client() as client:
                    await client.subscribe("hasp/#")
                    async for message in client.messages:
                        await self._handle_message(message)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                # TODO: use logger instead of print
                print(f'Error: {ex}; Reconnecting in {self._reconnect_interval_seconds} seconds ...')
                await asyncio.sleep(self._reconnect_interval_seconds)

    async def _handle_message(self, message: Message):
        for topic, callbacks in self._callbacks.items():
            if message.topic.matches(topic):
                for callback in callbacks:
                    await callback(message.topic, message.payload)
