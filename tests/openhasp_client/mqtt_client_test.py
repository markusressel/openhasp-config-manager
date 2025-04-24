from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from tests import TestBase


class TestMqttClient(TestBase):

    async def test_subscription(self):
        mqtt_client = MqttClient("localhost", 1883, "test", "test")

        async def callback(topic, payload):
            pass

        await mqtt_client.subscribe(topic="test", callback=callback)

        assert mqtt_client._callbacks == {
            "test": [callback]
        }

        await mqtt_client.cancel_callback(callback=callback)

    async def test_cancel_subscription(self):
        mqtt_client = MqttClient("localhost", 1883, "test", "test")

        async def callback(topic, payload):
            pass

        await mqtt_client.subscribe(topic="test", callback=callback)
        await mqtt_client.cancel_callback(callback=callback)

        assert mqtt_client._callbacks == {
            "test": []
        }
