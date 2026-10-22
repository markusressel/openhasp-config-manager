import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# (page, id) of an object, how the plate addresses it
ObjectKey = Tuple[int, int]

# properties a plate can't change on an existing object: the object has to be created again
_CREATION_PROPERTIES = {"obj", "parentid"}


@dataclass(frozen=True)
class LiveUpdate:
    """What to send to the plate to show the current state of a page."""

    # clear the page and send all of its objects again, instead of the commands below
    resend_page: bool = False
    # the objects to delete
    deletions: List[ObjectKey] = field(default_factory=list)
    # JSONL objects to send, in order: new objects in full, changed ones with only their page, id and changed properties
    objects: List[Dict[str, Any]] = field(default_factory=list)


class LivePage:
    """
    The objects of a page as they were last sent to the plate, to send only what changed since then.

    The plate can't be asked which objects it has, so this assumes that everything sent arrived.
    """

    def __init__(self):
        self._sent: Dict[ObjectKey, Dict[str, Any]] = {}

    def reset(self, objects: List[Dict[str, Any]]):
        """The page was sent in full (cleared, then all objects sent)."""
        self._sent = {_key(obj): copy.deepcopy(obj) for obj in objects}

    def update(self, objects: List[Dict[str, Any]]) -> Optional[LiveUpdate]:
        """
        :param objects: the objects the page shows now, in drawing order
        :return: what to send to show them, None if nothing changed. They count as sent afterwards.
        """
        current = {_key(obj): obj for obj in objects}
        sent, self._sent = self._sent, {key: copy.deepcopy(obj) for key, obj in current.items()}

        deletions = [key for key in sent if key not in current]
        changes = []
        for key, obj in current.items():
            before = sent.get(key)
            if before is None:
                changes.append(copy.deepcopy(obj))
                continue
            if set(before) - set(obj) or any(before.get(prop) != obj.get(prop) for prop in _CREATION_PROPERTIES):
                # a property can't be unset with a command, and the type of an object can't be changed
                return LiveUpdate(resend_page=True)
            changed = {prop: copy.deepcopy(value) for prop, value in obj.items() if before.get(prop) != value}
            if changed:
                changes.append({"page": key[0], "id": key[1], **changed})

        if not deletions and not changes:
            return None
        return LiveUpdate(deletions=deletions, objects=changes)


def _key(obj: Dict[str, Any]) -> ObjectKey:
    return obj.get("page"), obj.get("id")
