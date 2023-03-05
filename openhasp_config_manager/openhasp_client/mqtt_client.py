import paho.mqtt.client as paho

from openhasp_config_manager.openhasp_client.model.device import Device


class MqttClient:

    def __init__(self, host: str, port: int, mqtt_user: str, mqtt_password: str):
        self._mqtt_client_id = 'openhasp-config-manager'
        self._host = host
        self._port = port
        self._mqtt_user = mqtt_user
        self._mqtt_password = mqtt_password

    def publish(self, topic: str, payload: str):
        try:
            self._connect()
            result = self._client.publish(topic=topic, payload=payload)
            result.wait_for_publish()

            if not result.rc == paho.MQTT_ERR_SUCCESS:
                raise Exception(f'Code {result.rc} while sending message {result.mid}: {paho.error_string(result.rc)})')
        finally:
            self._client.disconnect()

    def watch(self, device: Device):
        pass

    def _connect(self):
        self._client = paho.Client(client_id=self._mqtt_client_id, protocol=paho.MQTTv5)
        self._client.username_pw_set(username=self._mqtt_user, password=self._mqtt_password)
        self._client.connect(self._host, self._port)
