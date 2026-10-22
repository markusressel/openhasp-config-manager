import asyncio

from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from tests import TestBase


class TestMqttClient(TestBase):
    async def test_subscription(self):
        mqtt_client = MqttClient("localhost", 1883, "test", "test")

        async def callback(topic, payload):
            pass

        await mqtt_client.subscribe(topic="test", callback=callback)

        assert mqtt_client._callbacks == {"test": [callback]}

        await mqtt_client.cancel_callback(callback=callback)

    async def test_cancel_subscription(self):
        mqtt_client = MqttClient("localhost", 1883, "test", "test")

        async def callback(topic, payload):
            pass

        await mqtt_client.subscribe(topic="test", callback=callback)
        await mqtt_client.cancel_callback(callback=callback)

        assert mqtt_client._callbacks == {"test": []}

    async def test_connection_listener(self):
        # GIVEN
        connected = asyncio.Event()
        events = []

        class _FakeClient:
            def __init__(self, fail: bool):
                self._fail = fail

            async def __aenter__(self):
                if self._fail:
                    raise ConnectionRefusedError("refused")
                return self

            async def __aexit__(self, *exc):
                pass

            async def subscribe(self, topic):
                pass

            @property
            def messages(self):
                return self._messages()

            async def _messages(self):
                await asyncio.Event().wait()
                yield  # pragma: no cover

        attempts = []

        class _MqttClient(MqttClient):
            def _create_mqtt_client(self):
                attempts.append(1)
                return _FakeClient(fail=len(attempts) == 1)

        mqtt_client = _MqttClient("localhost", 1883, "test", "test")
        mqtt_client._reconnect_interval_seconds = 0

        def listener(is_connected, error):
            events.append((is_connected, None if error is None else str(error)))
            if is_connected:
                connected.set()

        mqtt_client.add_connection_listener(listener)

        async def callback(topic, payload):
            pass

        # WHEN
        await mqtt_client.subscribe(topic="test", callback=callback)
        await asyncio.wait_for(connected.wait(), timeout=1)

        # THEN
        assert events == [(False, "refused"), (True, None)]

        mqtt_client.remove_connection_listener(listener)
        await mqtt_client.cancel_callback(callback=callback)
