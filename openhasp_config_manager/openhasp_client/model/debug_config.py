from dataclasses import dataclass


@dataclass
class DebugConfig:
    ansi: int
    baud: int
    tele: int
    host: str
    port: int
    proto: int
    log: int
