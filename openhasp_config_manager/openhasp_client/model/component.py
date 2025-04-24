from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Component:
    name: str
    type: str
    path: Path

    def __hash__(self):
        return hash((self.name, self.type, self.path))


@dataclass
class TextComponent(Component):
    content: str

    def __hash__(self):
        return super().__hash__()


@dataclass
class CmdComponent(TextComponent):
    commands: List[str]

    def __hash__(self):
        return super().__hash__()

@dataclass
class JsonlComponent(TextComponent):

    def __hash__(self):
        return super().__hash__()


@dataclass
class RawComponent(Component):
    content: bytes

    def __hash__(self):
        return super().__hash__()


@dataclass
class ImageComponent(RawComponent):

    def __hash__(self):
        return super().__hash__()


@dataclass
class FontComponent(RawComponent):

    def __hash__(self):
        return super().__hash__()
