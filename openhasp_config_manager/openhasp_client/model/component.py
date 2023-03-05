from dataclasses import dataclass
from pathlib import Path


@dataclass
class Component:
    name: str
    type: str
    path: Path
    content: str

    def __hash__(self):
        return hash((self.name, self.type, self.path))
