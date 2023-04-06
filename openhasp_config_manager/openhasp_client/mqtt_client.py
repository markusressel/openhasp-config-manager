import asyncio
from typing import Callable

from asyncio_mqtt import Client, MqttError


class MqttClient:

    def __init__(self, host: str, port: int, mqtt_user: str, mqtt_password: str):
        self._mqtt_client_id = 'openhasp-config-manager'
        self._host = host
        self._port = port
        self._mqtt_user = mqtt_user
        self._mqtt_password = mqtt_password
        self._reconnect_interval_seconds = 5

    async def publish(self, topic: str, payload: str):
        async with self._create_mqtt_client() as client:
            await client.publish(topic, payload=payload)

    async def subscribe(self, topic: str, callback: Callable):
        try:
            async with self._create_mqtt_client() as client:
                async with client.messages() as messages:
                    await client.subscribe(topic)
                    async for message in messages:
                        await callback(message.topic, message.payload)
        except MqttError:
            print(f'Connection lost; Reconnecting in {self._reconnect_interval_seconds} seconds ...')
            await asyncio.sleep(self._reconnect_interval_seconds)

    def _create_mqtt_client(self) -> Client:
        return Client(
            hostname=self._host,
            port=self._port,
            username=self._mqtt_user,
            password=self._mqtt_password,
            client_id=self._mqtt_client_id
        )
