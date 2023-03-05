from dataclasses import dataclass


@dataclass
class MqttConfig:
    name: str
    group: str
    host: str
    port: int
    user: str
    password: str
