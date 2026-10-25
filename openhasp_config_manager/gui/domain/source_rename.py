"""Renaming the id of an object in a .jsonl text, and what refers to it in the same text. Qt-free."""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from openhasp_config_manager.gui.domain.source_objects import SourceObject, object_at_line, scan_objects

_NUMBER = re.compile(r"\d+")


@dataclass(frozen=True)
class Rename:
    text: str
    # the lines (starting at 1) that changed
    lines: List[int]


def id_at_line(text: str, line: int) -> Optional[int]:
    """:return: the id of the object that contains a line, None if there is none or it is not a plain number"""
    objects = scan_objects(text)
    target = object_at_line(objects, line)
    prop = None if target is None else target.get("id")
    return int(prop.value) if prop is not None and prop.value and _NUMBER.fullmatch(prop.value) else None


def rename_object_id(text: str, line: int, new_id: int) -> Rename:
    """
    Change the `id` of the object at a line, and the `parentid` of the objects on the same page that have it as their parent.
    Other references (`p1b2` in strings, other files) are not changed.
    :raises ValueError: if there is no object with a plain number as its id at the line, or the page already has the new id
    """
    objects = scan_objects(text)
    target = object_at_line(objects, line)
    if target is None:
        raise ValueError("There is no object at the cursor")
    id_property = target.get("id")
    if id_property is None or id_property.value is None or not _NUMBER.fullmatch(id_property.value):
        raise ValueError("The id of this object is not a plain number")
    old_id = id_property.value
    pages = pages_of(objects)
    page = pages[target.index]
    if str(new_id) == old_id:
        return Rename(text, [])
    for other in objects:
        other_id = other.get("id")
        if (
            other.index != target.index
            and pages[other.index] == page
            and other_id is not None
            and other_id.value == str(new_id)
        ):
            raise ValueError(f"The id {new_id} is already used on this page (line {other.start_line})")

    edits: List[Tuple[int, int, int]] = [(id_property.value_line, id_property.value_start, id_property.value_end)]
    for other in objects:
        parent = other.get("parentid")
        if other.index != target.index and pages[other.index] == page and parent is not None and parent.value == old_id:
            edits.append((parent.value_line, parent.value_start, parent.value_end))

    lines = text.split("\n")
    for number, start, end in sorted(edits, reverse=True):
        lines[number - 1] = lines[number - 1][:start] + str(new_id) + lines[number - 1][end:]
    return Rename("\n".join(lines), sorted(number for number, _, _ in edits))


def pages_of(objects: List[SourceObject]) -> List[Optional[str]]:
    """The page of every object as written: an object without a page is on the page of the object before it."""
    pages: List[Optional[str]] = []
    page = None
    for obj in objects:
        prop = obj.get("page")
        if prop is not None:
            page = prop.value
        pages.append(page)
    return pages
