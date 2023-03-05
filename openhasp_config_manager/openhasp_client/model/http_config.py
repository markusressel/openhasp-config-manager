from dataclasses import dataclass


@dataclass
class HttpConfig:
    port: int
    user: str
    password: str
