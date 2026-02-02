from dataclasses import dataclass
from typing import List


@dataclass
class GuiConfig:
    idle1: int = None
    idle2: int = None
    bckl: int = None
    bcklinv: int = None
    rotate: int = None
    cursor: int = None
    invert: int = None
    calibration: List[int] = None
