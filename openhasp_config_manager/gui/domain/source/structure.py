"""
The brackets and objects of a text, kept up to date while it is edited, for the features of the text editor that run on every
keystroke (the matching bracket, the object at the cursor, folding). `update` reads only the lines that changed, and the questions
only read the lines they are about, so typing stays fast in a long file. The answers are those of `matching_bracket` and
`scan_objects` for the whole text. Qt-free.
"""

from dataclasses import replace
from typing import List, Optional, Tuple

from openhasp_config_manager.gui.domain.source.objects import SourceObject, object_at_line, scan_objects
from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, tokenize_line

_PAIRS = {"{": "}", "[": "]"}
_CLOSING = {closing: opening for opening, closing in _PAIRS.items()}

# the brackets of a line: (column, bracket)
type _Brackets = List[Tuple[int, str]]


class TextStructure:
    def __init__(self, language: Language):
        self._language = language
        self._lines: List[str] = []
        self._brackets: List[_Brackets] = []
        # in how many brackets of an object (counted like `scan_objects` does) every line starts, and the text ends
        self._depths: List[int] = [0]
        # how many objects start on every line, and how many end on it
        self._starts: List[int] = []
        self._ends: List[int] = []
        self.update("")

    def update(self, text: str):
        """Take a new version of the text: the lines that are the same at its start and at its end are not read again."""
        lines = text.split("\n")
        old = self._lines
        limit = min(len(old), len(lines))
        first = 0
        while first < limit and old[first] == lines[first]:
            first += 1
        if first == len(old) == len(lines):
            return
        same_end = 0
        while same_end < limit - first and old[-1 - same_end] == lines[-1 - same_end]:
            same_end += 1
        changed = [_brackets_of(line, self._language) for line in lines[first : len(lines) - same_end]]
        brackets = self._brackets[:first] + changed + self._brackets[len(old) - same_end :]

        depths, starts, ends = self._depths[: first + 1], self._starts[:first], self._ends[:first]
        shift = len(lines) - len(old)
        depth = depths[-1]
        for number in range(first, len(lines)):
            if number >= len(lines) - same_end and depth == self._depths[number - shift]:
                # the rest of the lines is the same and starts the same: so are their objects
                depths += self._depths[number - shift + 1 :]
                starts += self._starts[number - shift :]
                ends += self._ends[number - shift :]
                break
            depth, started, ended = _scan_line(brackets[number], depth)
            depths.append(depth)
            starts.append(started)
            ends.append(ended)
        self._lines, self._brackets = lines, brackets
        self._depths, self._starts, self._ends = depths, starts, ends

    def matching_bracket(self, line: int, column: int) -> Optional[Tuple[int, int]]:
        """
        :param line: starts at 0, like `column`
        :return: (line, column) of the bracket the one at a place pairs with (see `matching_bracket`), None if there is no bracket
            there or it has no partner
        """
        char = dict(self._brackets[line]).get(column) if 0 <= line < len(self._lines) else None
        if char is None:
            return None
        forward = char in _PAIRS
        partner = _PAIRS[char] if forward else _CLOSING[char]
        numbers = range(line, len(self._lines)) if forward else range(line, -1, -1)
        depth = 0
        for number in numbers:
            row = self._brackets[number] if forward else reversed(self._brackets[number])
            for other_column, other in row:
                if number == line and (other_column <= column if forward else other_column >= column):
                    continue
                if other == char:
                    depth += 1
                elif other == partner:
                    if depth == 0:
                        return number, other_column
                    depth -= 1
        return None

    def object_at_line(self, line: int) -> Optional[SourceObject]:
        """:return: the object that contains a line (starting at 1), as `scan_objects` of the whole text has it (.jsonl only)"""
        if self._language != Language.JSONL or not 1 <= line <= len(self._lines):
            return None
        # back to a line that starts outside of all objects: it starts the object of the line
        start = line - 1
        while self._depths[start] > 0:
            start -= 1
        if self._starts[start] == 0:
            return None
        end = start
        while end + 1 < len(self._lines) and self._depths[end + 1] > 0:
            end += 1
        found = object_at_line(scan_objects("\n".join(self._lines[start : end + 1])), line - start)
        return None if found is None else _moved(found, start, sum(self._starts[:start]))

    def foldable(self) -> List[Tuple[int, int]]:
        """:return: what `foldable` returns for the objects of the whole text (.jsonl only)"""
        if self._language != Language.JSONL:
            return []
        result = []
        # the line of the object that is open at the end of the line before
        open_line: Optional[int] = None
        for number in range(len(self._lines)):
            if open_line is not None and self._ends[number]:
                # the first object that ends on a line is the one that was open
                if number - open_line >= 2:
                    result.append((open_line + 1, number + 1))
                open_line = None
            if open_line is None and self._depths[number + 1] > 0:
                open_line = number
        if open_line is not None and len(self._lines) - 1 - open_line >= 2:
            result.append((open_line + 1, len(self._lines)))
        return result


def _brackets_of(line: str, language: Language) -> _Brackets:
    return [
        (token.start, line[token.start])
        for token in tokenize_line(line, language)
        if token.kind == TokenKind.SYMBOL and line[token.start] in "{}[]"
    ]


def _scan_line(brackets: _Brackets, depth: int) -> Tuple[int, int, int]:
    """:return: in how many brackets the next line starts, and how many objects start and end on this line (see `scan_objects`)"""
    started = ended = 0
    for _, char in brackets:
        if depth == 0:
            if char == "{":
                depth = 1
                started += 1
        elif char in "{[":
            depth += 1
        else:
            depth -= 1
            ended += depth == 0
    return depth, started, ended


def _moved(obj: SourceObject, lines: int, objects: int) -> SourceObject:
    """:return: an object of a part of a text, as it is in the whole text: after `lines` lines and `objects` objects"""
    properties = [
        replace(prop, line=prop.line + lines, value_line=prop.value_line + lines, value_end_line=prop.value_end_line + lines)
        for prop in obj.properties
    ]
    return replace(
        obj, index=obj.index + objects, start_line=obj.start_line + lines, end_line=obj.end_line + lines, properties=properties
    )
