import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

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


class LivePlate:
    """
    The objects of the pages of the plate as they were last sent to it, to send only what changed since then: also when the
    editor comes back to a page that was sent before, which then only needs to be shown.

    The plate can't be asked which objects it has, so this assumes that everything sent arrived, and that nothing else
    changes the objects meanwhile (start over with a new one when that may have happened, e.g. after a restart of the plate).
    """

    def __init__(self):
        self._sent: Dict[ObjectKey, Dict[str, Any]] = {}
        # the pages that were sent in full: the objects of the other pages are not known
        self._pages: Set[int] = set()

    def reset(self, page: int, objects: List[Dict[str, Any]]):
        """
        The page was sent in full (cleared, then all objects sent).
        :param objects: the objects of the page, and the global ones of page 0 (which were sent with them)
        """
        self._sent = {key: obj for key, obj in self._sent.items() if key[0] != page}
        self._sent.update({_key(obj): copy.deepcopy(obj) for obj in objects})
        self._pages.add(page)

    def update(self, page: int, objects: List[Dict[str, Any]]) -> Optional[LiveUpdate]:
        """
        :param objects: the objects the page shows now, in drawing order: its own and the global ones of page 0
        :return: what to send to show them, None if nothing changed. They count as sent afterwards, except for a page that
            has to be sent in full (`resend_page`): call `reset` once it was.
        """
        if page not in self._pages:
            return LiveUpdate(resend_page=True)
        pages = {page, 0}
        current = {_key(obj): obj for obj in objects}
        sent = {key: obj for key, obj in self._sent.items() if key[0] in pages}

        deletions = [key for key in sent if key not in current]
        changes = []
        for key, obj in current.items():
            before = sent.get(key)
            if before is None:
                changes.append(copy.deepcopy(obj))
                continue
            if set(before) - set(obj) or any(before.get(prop) != obj.get(prop) for prop in _CREATION_PROPERTIES):
                # a property can't be unset with a command, and the type of an object can't be changed
                self._pages.discard(page)
                return LiveUpdate(resend_page=True)
            changed = {prop: copy.deepcopy(value) for prop, value in obj.items() if before.get(prop) != value}
            if changed:
                changes.append({"page": key[0], "id": key[1], **changed})

        self._sent = {key: obj for key, obj in self._sent.items() if key[0] not in pages}
        self._sent.update({key: copy.deepcopy(obj) for key, obj in current.items()})
        if not deletions and not changes:
            return None
        return LiveUpdate(deletions=deletions, objects=changes)


def _key(obj: Dict[str, Any]) -> ObjectKey:
    return obj.get("page"), obj.get("id")


# Live preview runs on at most this many devices at once (see docs/tabs-and-shared-drafts.md, "Decisions")
MAX_LIVE_PREVIEWS = 10


def live_preview_refusal(device: str, live_devices: List[str]) -> Optional[str]:
    """
    :param device: the device to turn Live preview on for
    :param live_devices: the other devices with Live preview on
    :return: why Live preview can't be turned on for the device, None if it can. Nothing is turned off by itself: the user
        chooses which one to turn off.
    """
    if len(live_devices) < MAX_LIVE_PREVIEWS:
        return None
    return (
        f"Live preview runs on at most {MAX_LIVE_PREVIEWS} devices at once. Turn it off for one of them first, "
        f"to turn it on for {device}: {', '.join(sorted(live_devices))}."
    )
