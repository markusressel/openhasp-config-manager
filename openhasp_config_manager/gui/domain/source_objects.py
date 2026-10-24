"""
The objects of a .jsonl text and where their properties are, for the features of the text editor that work on objects:
folding, the object at the cursor, renaming ids. It reads the text the way `JsonlSourceEditor` does (the n-th object here is the
object with index n there), but also from text that is not valid yet. Qt-free.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from openhasp_config_manager.gui.domain.source_syntax import Language, Token, TokenKind, tokenize_line


@dataclass(frozen=True)
class SourceProperty:
    key: str
    # starts at 1
    line: int
    # where the value is: from the first character (line starting at 1, column starting at 0) to the end of the last
    value_line: int
    value_start: int
    value_end_line: int
    value_end: int
    # the value as written, None if it is spread over several lines
    value: Optional[str]


@dataclass(frozen=True)
class SourceObject:
    index: int
    # the lines (starting at 1) of the opening and of the closing bracket. An object that is not closed reaches to the last line.
    start_line: int
    end_line: int
    properties: List[SourceProperty]

    def get(self, key: str) -> Optional[SourceProperty]:
        return next((prop for prop in self.properties if prop.key == key), None)


class _PropertyBuilder:
    def __init__(self, line: int):
        self.line = line
        self.key_text = ""
        self.has_colon = False
        self.first: Optional[tuple] = None
        self.last: Optional[tuple] = None

    def add(self, number: int, line: str, token: Token):
        if not self.has_colon:
            self.key_text += token.text(line)
            return
        if self.first is None:
            self.first = (number, token.start)
        self.last = (number, token.end)

    def build(self, lines: List[str]) -> Optional[SourceProperty]:
        if self.first is None or self.last is None:
            return None
        first_line, start = self.first
        last_line, end = self.last
        value = lines[first_line - 1][start:end] if first_line == last_line else None
        return SourceProperty(self.key_text.strip('"'), self.line, first_line, start, last_line, end, value)


def scan_objects(text: str) -> List[SourceObject]:
    """:return: the objects of a text, in the order of the file"""
    lines = text.split("\n")
    objects: List[SourceObject] = []
    depth = 0
    start_line = 0
    properties: List[SourceProperty] = []
    builder: Optional[_PropertyBuilder] = None

    def finish_property():
        nonlocal builder
        if builder is not None and (prop := builder.build(lines)) is not None:
            properties.append(prop)
        builder = None

    for number, line in enumerate(lines, start=1):
        for token in tokenize_line(line, Language.JSONL):
            if token.kind == TokenKind.COMMENT:
                continue
            char = line[token.start] if token.kind == TokenKind.SYMBOL else ""
            if depth == 0:
                if char == "{":
                    depth, start_line, properties = 1, number, []
                continue
            if char in ("{", "["):
                depth += 1
            elif char in ("}", "]"):
                depth -= 1
                if depth == 0:
                    finish_property()
                    objects.append(SourceObject(len(objects), start_line, number, properties))
                    continue
            elif depth == 1 and char == ",":
                finish_property()
                continue
            elif depth == 1 and char == ":" and builder is not None and not builder.has_colon:
                builder.has_colon = True
                continue
            if depth == 1 and builder is None and token.kind == TokenKind.KEY:
                builder = _PropertyBuilder(number)
            if builder is not None:
                builder.add(number, line, token)
    if depth > 0:
        finish_property()
        objects.append(SourceObject(len(objects), start_line, len(lines), properties))
    return objects


def object_at_line(objects: List[SourceObject], line: int) -> Optional[SourceObject]:
    """:return: the object that contains a line (starting at 1), None for lines between the objects"""
    return next((obj for obj in objects if obj.start_line <= line <= obj.end_line), None)


def foldable(objects: List[SourceObject]) -> List[Tuple[int, int]]:
    """:return: the objects that can be folded as (first line, last line), starting at 1. The lines in between are hidden."""
    return [(obj.start_line, obj.end_line) for obj in objects if obj.end_line - obj.start_line >= 2]


def fold_ranges(text: str) -> List[Tuple[int, int]]:
    return foldable(scan_objects(text))
