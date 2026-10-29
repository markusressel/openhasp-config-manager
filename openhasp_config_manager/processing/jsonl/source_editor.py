import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import orjson

from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import JsonlPreProcessor


@dataclass
class _Property:
    key: str
    # where the name starts (its quote)
    key_start: int
    # where the line of the key starts, for the indentation of new properties
    line_start: int
    value_start: int
    value_end: int


@dataclass
class _ObjectSpan:
    start: int
    # exclusive, after the closing brace
    end: int
    properties: List[_Property] = field(default_factory=list)


class JsonlSourceEditor:
    """
    Changes the objects of a .jsonl source file while keeping everything that is not changed as it is written:
    comments, formatting, the order of properties and templates.

    The files allow "//" comments and a trailing comma after the last property (see JsonlPreProcessor).
    """

    def __init__(self, content: str):
        self._content = content
        self._objects = _scan_objects(content)

    @property
    def object_count(self) -> int:
        return len(self._objects)

    def line_of(self, index: int) -> int:
        """:return: the line (starting at 1) on which the object with this index starts"""
        return self._content.count("\n", 0, self._objects[index].start) + 1

    def apply(
        self,
        changes: Dict[int, Dict[str, Any]],
        deletions: Set[int],
        additions: List[Dict[str, Any]],
        removals: Optional[Dict[int, Set[str]]] = None,
    ) -> str:
        """
        :param changes: object index -> the properties to set (added if the object does not have them yet)
        :param deletions: the indices of the objects to delete
        :param additions: objects to append to the end of the file, one line each
        :param removals: object index -> the properties to remove (with the comma that separates them)
        :return: the new content
        """
        removals = removals or {}
        for index in set(changes) | deletions | set(removals):
            if not 0 <= index < len(self._objects):
                raise IndexError(f"No object with index {index}, the source has {len(self._objects)}")

        # (start, end, replacement) on the original content, applied from the end so the offsets stay valid
        edits: List[Tuple[int, int, str]] = []
        for index, properties in changes.items():
            if index not in deletions:
                edits.extend(self._property_edits(self._objects[index], properties))
        for index, keys in removals.items():
            if index not in deletions:
                edits.extend(self._removal_edits(self._objects[index], keys))
        for index in deletions:
            edits.append(self._deletion_edit(self._objects[index]))

        result = self._content
        for start, end, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
            result = result[:start] + replacement + result[end:]

        if additions:
            if result and not result.endswith("\n"):
                result += "\n"
            result += "".join(f"{_dump(obj)}\n" for obj in additions)
        return result

    def _property_edits(self, span: _ObjectSpan, properties: Dict[str, Any]) -> List[Tuple[int, int, str]]:
        edits = []
        existing = {prop.key: prop for prop in span.properties}
        new_properties = {key: value for key, value in properties.items() if key not in existing}
        for key, value in properties.items():
            if key in existing:
                prop = existing[key]
                edits.append((prop.value_start, prop.value_end, _dump(value)))

        if new_properties:
            multiline = "\n" in self._content[span.start : span.end]
            if span.properties:
                last = span.properties[-1]
                position = last.value_end
                indent = _indentation(self._content, last.line_start)
                prefix = ","
            else:
                position = span.start + 1
                indent = "  "
                prefix = ""
            parts = []
            for key, value in new_properties.items():
                separator = f"\n{indent}" if multiline else " "
                parts.append(f"{prefix}{separator}{_dump(key)}: {_dump(value)}")
                prefix = ","
            edits.append((position, position, "".join(parts)))
        return edits

    def _removal_edits(self, span: _ObjectSpan, keys: Set[str]) -> List[Tuple[int, int, str]]:
        """
        Each run of removed properties is cut out with the comma before it (after the value of the property before it), or,
        at the start of the object, up to the next property, so the formatting of the rest stays.
        """
        missing = keys - {prop.key for prop in span.properties}
        if missing:
            raise KeyError(f"The object has no {', '.join(sorted(missing))} to remove")
        edits = []
        properties = span.properties
        position = 0
        while position < len(properties):
            if properties[position].key not in keys:
                position += 1
                continue
            first = position
            while position < len(properties) and properties[position].key in keys:
                position += 1
            last = properties[position - 1]
            if first > 0:
                edits.append((properties[first - 1].value_end, last.value_end, ""))
            elif position < len(properties):
                edits.append((properties[first].key_start, properties[position].key_start, ""))
            else:
                # every property: the object stays, empty
                end = _skip_whitespace_and_comments(self._content, last.value_end)
                if self._content[end] == ",":
                    end += 1
                edits.append((properties[first].key_start, end, ""))
        return edits

    def _deletion_edit(self, span: _ObjectSpan) -> Tuple[int, int, str]:
        start, end = span.start, span.end
        # remove the whole line(s) if the object is alone on them
        line_start = self._content.rfind("\n", 0, start) + 1
        line_end = self._content.find("\n", end)
        line_end = len(self._content) if line_end == -1 else line_end + 1
        if not self._content[line_start:start].strip() and not self._content[end:line_end].strip():
            return line_start, line_end, ""
        return start, end, ""


def verify_jsonl_source(content: str, expected_objects: List[Dict[str, Any]]):
    """
    Parses the content like a deployment does and checks that it has exactly the expected objects.
    :raises ValueError: if not
    """
    preprocessor = JsonlPreProcessor()
    parsed = [
        orjson.loads(preprocessor.cleanup_object_for_json_parsing(ob)) for ob in preprocessor.split_jsonl_objects(content)
    ]
    if parsed != expected_objects:
        raise ValueError(f"The edited source does not contain the expected objects:\n{content}")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _indentation(content: str, line_start: int) -> str:
    end = line_start
    while end < len(content) and content[end] in " \t":
        end += 1
    return content[line_start:end]


def _skip_whitespace_and_comments(content: str, i: int) -> int:
    while i < len(content):
        if content[i].isspace():
            i += 1
        elif content.startswith("//", i):
            newline = content.find("\n", i)
            i = len(content) if newline == -1 else newline + 1
        else:
            break
    return i


def _skip_string(content: str, i: int) -> int:
    """:return: the index after the string starting at i (a quote)"""
    i += 1
    while content[i] != '"':
        i += 2 if content[i] == "\\" else 1
    return i + 1


def _skip_value(content: str, i: int) -> int:
    """:return: the index after the value starting at i"""
    if content[i] == '"':
        return _skip_string(content, i)
    if content[i] in "{[":
        depth = 0
        while True:
            i = _skip_whitespace_and_comments(content, i)
            char = content[i]
            if char == '"':
                i = _skip_string(content, i)
                continue
            if char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
    # number, true, false, null
    start = i
    while i < len(content) and content[i] not in ",}]\n\r\t " and not content.startswith("//", i):
        i += 1
    if i == start:
        raise ValueError(f"Expected a value at offset {start}")
    return i


def _scan_object(content: str, start: int) -> _ObjectSpan:
    span = _ObjectSpan(start=start, end=start)
    i = start + 1
    while True:
        i = _skip_whitespace_and_comments(content, i)
        if content[i] == "}":
            span.end = i + 1
            return span
        if content[i] != '"':
            raise ValueError(f"Expected a property name at offset {i}")
        line_start = content.rfind("\n", 0, i) + 1
        key_start = i
        key_end = _skip_string(content, i)
        key = json.loads(content[i:key_end])
        i = _skip_whitespace_and_comments(content, key_end)
        if content[i] != ":":
            raise ValueError(f"Expected ':' at offset {i}")
        i = _skip_whitespace_and_comments(content, i + 1)
        value_end = _skip_value(content, i)
        span.properties.append(
            _Property(key=key, key_start=key_start, line_start=line_start, value_start=i, value_end=value_end)
        )
        i = _skip_whitespace_and_comments(content, value_end)
        if content[i] == ",":
            i += 1


def _scan_objects(content: str) -> List[_ObjectSpan]:
    objects = []
    i = 0
    while True:
        i = _skip_whitespace_and_comments(content, i)
        if i >= len(content):
            return objects
        if content[i] != "{":
            raise ValueError(f"Expected an object at offset {i}")
        span = _scan_object(content, i)
        objects.append(span)
        i = span.end
