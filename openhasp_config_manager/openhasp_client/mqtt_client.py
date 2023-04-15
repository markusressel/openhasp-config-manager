import asyncio
import json
import uuid
from typing import Callable, List, Dict

from asyncio_mqtt import Client, Message


class MqttClient:

    def __init__(self, host: str, port: int, mqtt_user: str, mqtt_password: str):
        self._mqtt_client_id = 'openhasp-config-manager'
        self._host = host
        self._port = port
        self._mqtt_user = mqtt_user
        self._mqtt_password = mqtt_password
        self._reconnect_interval_seconds = 5

        self._mqtt_client_task: asyncio.Task = None
        self._callbacks: Dict[str, List[callable]] = {}
        self.__mqtt_client: Client = None

    async def publish(self, topic: str, payload: any):
        async with self._create_mqtt_client() as client:
            if isinstance(payload, dict):
                payload = json.dumps(payload)

            await client.publish(topic, payload=payload)

    async def subscribe(self, topic: str, callback: Callable):
        if topic not in self._callbacks:
            self._callbacks[topic] = []
        if callback not in self._callbacks[topic]:
            self._callbacks[topic].append(callback)

        if self._callbacks:
            await self._start_mqtt_client_task()
        else:
            await self._stop_mqtt_client_task()

    def _create_mqtt_client(self) -> Client:
        return Client(
            hostname=self._host,
            port=self._port,
            username=self._mqtt_user,
            password=self._mqtt_password,
            client_id=f"{self._mqtt_client_id}-{uuid.uuid4()}",
        )

    async def _start_mqtt_client_task(self):
        if self._mqtt_client_task is None:
            self._mqtt_client_task = asyncio.create_task(self._mqtt_client_task_function())

    async def _stop_mqtt_client_task(self):
        if self._mqtt_client_task is not None:
            self._mqtt_client_task.cancel()
            self._mqtt_client_task = None

    async def _mqtt_client_task_function(self):
        while True:
            try:
                async with self._create_mqtt_client() as client:
                    async with client.messages() as messages:
                        await client.subscribe("hasp/#")
                        async for message in messages:
                            await self._handle_message(message)
            except Exception as ex:
                # TODO: use logger instead of print
                print(f'Error: {ex}; Reconnecting in {self._reconnect_interval_seconds} seconds ...')
                await asyncio.sleep(self._reconnect_interval_seconds)

    async def _handle_message(self, message: Message):
        for topic, callbacks in self._callbacks.items():
            if message.topic.matches(topic):
                for callback in callbacks:
                    await callback(message.topic, message.payload)
