from dataclasses import dataclass


@dataclass
class TelnetConfig:
    enable: int
    port: int
