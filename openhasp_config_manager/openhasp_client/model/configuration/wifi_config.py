from dataclasses import dataclass


@dataclass
class WifiConfig:
    ssid: str
    password: str
