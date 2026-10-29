from dataclasses import dataclass, replace
from typing import Callable, Generic, Hashable, List, Optional, TypeVar

S = TypeVar("S")


@dataclass(frozen=True)
class Step(Generic[S]):
    """An edit, as the states before and after it."""

    description: str
    before: S
    after: S
    # edits with the same key, one right after the other, are one step (e.g. typing into a property, nudging with the keys)
    merge_key: Optional[Hashable] = None


class EditHistory(Generic[S]):
    """
    Undo and redo of edits. The history keeps whole states (the caller restores them), so undoing doesn't depend on how an
    edit was made.
    """

    def __init__(self, limit: int = 500):
        self._limit = limit
        self._undo: List[Step[S]] = []
        self._redo: List[Step[S]] = []

    def push(self, description: str, before: S, after: S, merge_key: Optional[Hashable] = None):
        """Record an edit. Redo is not possible afterwards."""
        self._redo.clear()
        top = self._undo[-1] if self._undo else None
        if merge_key is not None and top is not None and top.merge_key == merge_key:
            if after == top.before:
                # edited back to where the merged edits started: nothing to undo
                self._undo.pop()
            else:
                self._undo[-1] = replace(top, after=after)
            return
        self._undo.append(Step(description, before, after, merge_key))
        del self._undo[: -self._limit]

    def seal(self):
        """The next edit is a step of its own, even if it has the same merge key (e.g. another object was selected)."""
        if self._undo and self._undo[-1].merge_key is not None:
            self._undo[-1] = replace(self._undo[-1], merge_key=None)

    def undo(self) -> Optional[Step[S]]:
        """:return: the step to undo (restore its `before`), None if there is none"""
        if not self._undo:
            return None
        step = replace(self._undo.pop(), merge_key=None)
        self._redo.append(step)
        return step

    def redo(self) -> Optional[Step[S]]:
        """:return: the step to redo (restore its `after`), None if there is none"""
        if not self._redo:
            return None
        step = self._redo.pop()
        self._undo.append(step)
        return step

    @property
    def undo_description(self) -> Optional[str]:
        return self._undo[-1].description if self._undo else None

    @property
    def redo_description(self) -> Optional[str]:
        return self._redo[-1].description if self._redo else None

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def drop(self, dropped: Callable[[Step[S]], bool]):
        """Forget the steps (to undo and to redo) for which `dropped` is true, e.g. those of a file that was loaded again."""
        self._undo = [step for step in self._undo if not dropped(step)]
        self._redo = [step for step in self._redo if not dropped(step)]

    def mapped(self, translate: Callable[[S], S]) -> "EditHistory[S]":
        """:return: a copy with every state translated, e.g. after the states were saved and are read back differently"""
        result = EditHistory(self._limit)
        result._undo = [replace(step, before=translate(step.before), after=translate(step.after)) for step in self._undo]
        result._redo = [replace(step, before=translate(step.before), after=translate(step.after)) for step in self._redo]
        return result
