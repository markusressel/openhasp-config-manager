import paho.mqtt.client as paho

from openhasp_config_manager.model import Device
from openhasp_config_manager.ui.util import echo


class MqttClient:

    def __init__(self, host: str, port: int, mqtt_user: str, mqtt_password: str):
        mqtt_client_id = 'openhasp-config-manager'
        self._client = paho.Client(client_id=mqtt_client_id, protocol=paho.MQTTv5)
        self._client.username_pw_set(username=mqtt_user, password=mqtt_password)
        self._client.connect(host, port)

    def publish(self, topic: str, payload: str):
        result = self._client.publish(topic=topic, payload=payload)
        result.wait_for_publish()

        if not result.rc == paho.MQTT_ERR_SUCCESS:
            echo(f'Code {result.rc} while sending message {result.mid}: {paho.error_string(result.rc)}',
                 color="red")

        self._client.disconnect()

    def watch(self, device: Device):
        pass
