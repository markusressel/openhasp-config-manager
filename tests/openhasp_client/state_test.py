import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class FakeMqttClient:
    """Keeps the callbacks like MqttClient, without a broker."""

    def __init__(self):
        self.callbacks = {}

    async def subscribe(self, topic, callback):
        self.callbacks.setdefault(topic, []).append(callback)

    async def cancel_callback(self, topic=None, callback=None):
        for topic in self.callbacks:
            self.callbacks[topic] = [c for c in self.callbacks[topic] if c != callback]

    async def publish(self, topic, payload):
        for callback in list(self.callbacks.get(topic, [])):
            await callback(topic, orjson.dumps(payload))


class TestGetObjectProperty(TestBase):
    def _client(self, tmp_path, monkeypatch, replies):
        """:param replies: for each command, what the plate publishes on the object's state topic"""
        device = ConfigManager(self.cfg_root, tmp_path, VariableManager(self.cfg_root)).analyze()[0]
        client = OpenHaspClient(device)
        mqtt = FakeMqttClient()
        monkeypatch.setattr(client, "_mqtt_client", mqtt)

        async def command(keyword=None, params=None):
            obj = keyword.split(".")[0]
            for payload in replies.get(keyword, []):
                await mqtt.publish(f"hasp/{device.config.mqtt.name}/state/{obj}", payload)

        monkeypatch.setattr(client, "command", command)
        return client, mqtt

    async def test_a_late_reply_for_another_property_is_not_taken(self, tmp_path, monkeypatch):
        # GIVEN the reply to an earlier request for "h" arrives while "w" is asked for
        client, _ = self._client(tmp_path, monkeypatch, {"p1b45.w": [{"h": 108}, {"w": 192}]})

        # WHEN
        width = await client.get_object_property("p1b45", "w")

        # THEN
        assert width == 192

    async def test_only_other_properties_is_a_timeout(self, tmp_path, monkeypatch):
        # GIVEN
        client, _ = self._client(tmp_path, monkeypatch, {"p1b45.w": [{"h": 108}]})

        # WHEN
        width = await client.get_object_property("p1b45", "w", timeout=0.01)

        # THEN
        assert width is None

    async def test_the_callback_of_a_request_is_removed(self, tmp_path, monkeypatch):
        # GIVEN
        client, mqtt = self._client(tmp_path, monkeypatch, {"p1b45.w": [{"w": 192}]})

        # WHEN one request is answered, one times out
        await client.get_object_property("p1b45", "w")
        await client.get_object_property("p1b45", "h", timeout=0.01)

        # THEN
        assert not any(mqtt.callbacks.values())

    async def test_a_state_that_is_not_json_is_returned_as_text(self, tmp_path, monkeypatch):
        # GIVEN
        client, mqtt = self._client(tmp_path, monkeypatch, {})

        async def command(keyword=None, params=None):
            for callback in list(mqtt.callbacks[f"hasp/{client._device.config.mqtt.name}/state/backlight"]):
                await callback("", b"on")

        monkeypatch.setattr(client, "command", command)

        # WHEN
        state = await client.get_state(command="backlight")

        # THEN
        assert state == "on"
