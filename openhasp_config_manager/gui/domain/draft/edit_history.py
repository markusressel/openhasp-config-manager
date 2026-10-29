from dataclasses import dataclass, replace
from typing import AbstractSet, Callable, FrozenSet, Generic, Hashable, List, Optional, TypeVar

S = TypeVar("S")


@dataclass(frozen=True)
class Step(Generic[S]):
    """An edit, as the states before and after it."""

    description: str
    before: S
    after: S
    # edits with the same key, one right after the other, are one step (e.g. typing into a property, nudging with the keys)
    merge_key: Optional[Hashable] = None
    # the files the edit changed (e.g. their keys); None: all of them
    files: Optional[FrozenSet[Hashable]] = None

    def changes(self, files: Optional[AbstractSet[Hashable]]) -> bool:
        """:return: whether the step changed one of the files (None: any file)"""
        return files is None or self.files is None or not self.files.isdisjoint(files)


class BlockedStepError(Exception):
    """A step can't be undone (or redone) as a whole: some of its files were changed by newer steps."""

    def __init__(self, step: Step, files: FrozenSet[Hashable]):
        super().__init__(f"{step.description}: changed since in {sorted(map(str, files))}")
        self.step = step
        # the files of the step that newer steps changed
        self.files = files


class EditHistory(Generic[S]):
    """
    Undo and redo of edits. The history keeps whole states (the caller restores them), so undoing doesn't depend on how an
    edit was made.

    Each step can know the files it changed: undo and redo can then be limited to some files (those a view shows), like
    in IntelliJ. A step is undone (redone) only as a whole, and only if it is the newest step to undo (to redo) in each of
    its files; otherwise `BlockedStepError` names the files that changed since. Merging and `seal` work on the newest
    step of all files.
    """

    def __init__(self, limit: int = 500):
        self._limit = limit
        # oldest first: the steps of one file are in the order they were made, the newest last
        self._undo: List[Step[S]] = []
        # the step that is redone next last
        self._redo: List[Step[S]] = []

    def push(
        self,
        description: str,
        before: S,
        after: S,
        merge_key: Optional[Hashable] = None,
        files: Optional[AbstractSet[Hashable]] = None,
    ):
        """
        Record an edit. The steps to redo of the files it changed can't be redone afterwards, and neither can those that
        would be redone after one of them in one of its files (their states before would never come back).
        :param files: the files the edit changed, None: all of them (nothing can be redone afterwards)
        """
        files = None if files is None else frozenset(files)
        self._drop_redo(files)
        top = self._undo[-1] if self._undo else None
        if merge_key is not None and top is not None and top.merge_key == merge_key:
            if after == top.before:
                # edited back to where the merged edits started: nothing to undo
                self._undo.pop()
            else:
                merged = None if files is None or top.files is None else top.files | files
                self._undo[-1] = replace(top, after=after, files=merged)
            return
        self._undo.append(Step(description, before, after, merge_key, files))
        del self._undo[: -self._limit]

    def _drop_redo(self, files: Optional[FrozenSet[Hashable]]):
        if files is None:
            self._redo.clear()
            return
        # the files whose states before the steps to redo are gone, None: all of them
        gone: Optional[AbstractSet[Hashable]] = files
        kept = []
        # in the order they would be redone
        for step in reversed(self._redo):
            if step.changes(gone):
                gone = None if gone is None or step.files is None else gone | step.files
            else:
                kept.append(step)
        self._redo = kept[::-1]

    def seal(self):
        """The next edit is a step of its own, even if it has the same merge key (e.g. another object was selected)."""
        if self._undo and self._undo[-1].merge_key is not None:
            self._undo[-1] = replace(self._undo[-1], merge_key=None)

    def next_undo(self, files: Optional[AbstractSet[Hashable]] = None) -> Optional[Step[S]]:
        """:return: the step `undo` undoes for the files (None: all), also if it is blocked (see `blocked_by`)"""
        return _newest(self._undo, files)

    def next_redo(self, files: Optional[AbstractSet[Hashable]] = None) -> Optional[Step[S]]:
        """:return: the step `redo` redoes for the files (None: all), also if it is blocked (see `blocked_by`)"""
        return _newest(self._redo, files)

    def blocked_by(self, step: Step[S]) -> FrozenSet[Hashable]:
        """
        :return: the files of a step to undo (or to redo) that newer steps to undo (or steps to redo before it) changed:
            it can't be undone (redone) while there are any
        """
        steps = self._undo if any(other is step for other in self._undo) else self._redo
        return _overlap(step, _newer(steps, step))

    def undo(self, files: Optional[AbstractSet[Hashable]] = None) -> Optional[Step[S]]:
        """
        :param files: undo the newest step that changed one of them, None: the newest step
        :return: the step to undo (restore its `before` in its files), None if there is none
        :raise BlockedStepError: if newer steps changed some of its files
        """
        step = self._take(self._undo, files)
        if step is None:
            return None
        step = replace(step, merge_key=None)
        self._redo.append(step)
        return step

    def redo(self, files: Optional[AbstractSet[Hashable]] = None) -> Optional[Step[S]]:
        """:return: the step to redo (restore its `after` in its files), None if there is none (see `undo`)"""
        step = self._take(self._redo, files)
        if step is not None:
            self._undo.append(step)
        return step

    def _take(self, steps: List[Step[S]], files: Optional[AbstractSet[Hashable]]) -> Optional[Step[S]]:
        step = _newest(steps, files)
        if step is None:
            return None
        newer = _newer(steps, step)
        if newer:
            raise BlockedStepError(step, _overlap(step, newer))
        del steps[_position(steps, step)]
        return step

    @property
    def undo_description(self) -> Optional[str]:
        """What `undo` undoes for all files."""
        return self._undo[-1].description if self._undo else None

    @property
    def redo_description(self) -> Optional[str]:
        """What `redo` redoes for all files."""
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


def _newest(steps: List[Step[S]], files: Optional[AbstractSet[Hashable]]) -> Optional[Step[S]]:
    """:return: the last of the steps that changed one of the files (None: any)"""
    return next((step for step in reversed(steps) if step.changes(files)), None)


def _position(steps: List[Step[S]], step: Step[S]) -> int:
    # by identity: steps with the same states are equal
    return next(i for i, other in enumerate(steps) if other is step)


def _newer(steps: List[Step[S]], step: Step[S]) -> List[Step[S]]:
    """:return: the steps after one in the list that changed one of its files"""
    return [other for other in steps[_position(steps, step) + 1 :] if other.changes(step.files)]


def _overlap(step: Step[S], others: List[Step[S]]) -> FrozenSet[Hashable]:
    """:return: the files of the step that the others changed (those the others know if the step doesn't know its own)"""
    result: FrozenSet[Hashable] = frozenset()
    for other in others:
        if step.files is None or other.files is None:
            result |= step.files or other.files or frozenset()
        else:
            result |= step.files & other.files
    return result
