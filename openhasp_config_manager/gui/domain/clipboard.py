import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# how far each paste of the same objects to the same spot is moved, so it doesn't hide the previous one
PASTE_OFFSET = 10


def objects_to_text(sources: List[Dict]) -> str:
    """:return: the objects as JSONL, as they are written in a .jsonl file"""
    return "".join(json.dumps(source, ensure_ascii=False) + "\n" for source in sources)


def objects_from_text(text: str) -> List[Dict]:
    """:return: the objects of a JSONL text, or an empty list if it isn't one (every line must be an openHASP object)"""
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(obj, dict) or "obj" not in obj:
            return []
        result.append(obj)
    return result


def with_descendants(page_objects: List[Dict], selected: List[Dict]) -> List[Dict]:
    """
    :param page_objects: the objects of a page
    :return: the selected objects and the objects inside of them (parentid), in the order of the page
    """
    ids = {obj.get("id") for obj in selected}
    while True:
        children = {obj.get("id") for obj in page_objects if obj.get("parentid") in ids} - ids
        if not children:
            break
        ids |= children
    return [obj for obj in page_objects if obj.get("id") in ids]


@dataclass
class PasteCascade:
    """
    Moves repeated pastes of the same objects to the same spot a bit further each time, so they don't hide each other.
    """

    _last: Optional[Tuple[str, Optional[Tuple[int, int]]]] = None
    _count: int = 0

    def reset(self):
        self._last = None
        self._count = 0

    def next_offset(self, text: str, position: Optional[Tuple[int, int]]) -> int:
        """
        :param text: what is pasted
        :param position: where it is pasted, None for the position of the originals
        :return: how far to move the pasted objects (right and down)
        """
        key = (text, position)
        self._count = self._count + 1 if key == self._last else 0
        self._last = key
        # at the position of the originals, the first paste would cover them
        steps = self._count + (1 if position is None else 0)
        return steps * PASTE_OFFSET
