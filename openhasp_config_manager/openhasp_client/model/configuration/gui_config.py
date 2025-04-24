from dataclasses import dataclass
from typing import List


@dataclass
class GuiConfig:
    idle1: int
    idle2: int
    bckl: int
    bcklinv: int
    rotate: int
    cursor: int
    invert: int
    calibration: List[int]
