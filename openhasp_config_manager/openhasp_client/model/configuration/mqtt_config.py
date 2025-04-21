from dataclasses import dataclass


@dataclass
class MqttConfig:
    name: str
    host: str
    port: int
    user: str
    password: str
    topic: "MqttTopicConfig"


@dataclass
class MqttTopicConfig:
    node: str
    group: str
    broadcast: str
    hass: str
