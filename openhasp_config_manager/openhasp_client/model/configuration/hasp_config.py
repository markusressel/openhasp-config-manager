from dataclasses import dataclass


@dataclass
class HaspConfig:
    startpage: int
    startdim: int
    theme: int
    color1: str
    color2: str
    font: str
    pages: str
