"""The draft of the files of a config directory, shared by the drafts of its devices (`PlateSession`)."""

import copy
import itertools
import weakref
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Set, Tuple, TypeVar

from openhasp_config_manager.gui.domain.draft.edit_history import EditHistory, Step
from openhasp_config_manager.gui.domain.draft.model import (
    ChangeKind,
    ComponentChanges,
    ComponentSource,
    DraftChange,
    DraftState,
    FileState,
    PartDraft,
    PartObject,
)
from openhasp_config_manager.processing.jsonl.includes import is_directive

if TYPE_CHECKING:
    from openhasp_config_manager.gui.domain.draft.session import PlateSession

T = TypeVar("T")


@dataclass
class FileDraft:
    """A page file (a jsonl component) as the draft has it, for every device that shows it."""

    # the file as it was read from disk (or saved)
    component: ComponentSource
    # its objects that are not directives, in the order of the draft: the rendered objects of the devices share their sources
    objects: List[PartObject]
    # the index of a directive (`!include`) in the file -> the directive as the draft has it
    directives: Dict[int, Dict[str, Any]]

    def indexed_sources(self) -> List[Tuple[Optional[int], Dict[str, Any], Optional[PartObject]]]:
        """:return: (index in the file, source, its object; None for a directive) of the file as the draft would write it"""
        return with_directives(self.directives, [(obj.index, obj.source, obj) for obj in self.objects])


def with_directives(
    directives: Dict[int, Dict[str, Any]], objects: List[Tuple[Optional[int], Dict[str, Any], T]]
) -> List[Tuple[Optional[int], Dict[str, Any], Optional[T]]]:
    """
    :param objects: (index in the file, None for an added object; source; anything) of the objects of a file that are not
        directives, in the order of the draft
    :return: them with the directives (anything is None for them), which are in the order of the file, also those that
        include nothing, so none of them is further down than in the file: the expansion finds their lines in the file.
    """
    remaining = sorted(directives.items())
    result: List[Tuple[Optional[int], Dict[str, Any], Optional[T]]] = []
    for index, source, value in objects:
        while remaining and (index is None or remaining[0][0] < index):
            directive_index, directive = remaining.pop(0)
            result.append((directive_index, directive, None))
        result.append((index, source, value))
    return result + [(index, directive, None) for index, directive in remaining]


class ConfigDraft:
    """
    The files of a config directory as the draft has them, for all devices: the page files (`FileDraft`) and the parts
    (`PartDraft`), keyed by their paths (like the component keys and the part keys of a `PlateSession`).

    The draft of a device (`PlateSession`) renders the files it shows with the variables of the device, and changes them. An
    edit through one of them changes the files here, and every other one that shows a changed file renders it again and tells
    its listeners (`DraftChange`), as for its own edits. A file is loaded once: a device that is loaded later uses its draft,
    with its changes. The files of one device (`devices/<name>/...`) are shown by that device only.

    The undo history is one for all files, but it keeps the state of every file on its own (`DraftState`): an undo restores
    only the files its step changed.
    """

    def __init__(self):
        self.files: OrderedDict[str, FileDraft] = OrderedDict()
        self.parts: OrderedDict[str, PartDraft] = OrderedDict()
        self.history: EditHistory[DraftState] = EditHistory()
        self._uids = itertools.count()
        self._part_uids = itertools.count()
        # the drafts of the devices that show files of this draft
        self._sessions: List[weakref.ref] = []
        # the keys of the files and parts that differ from their files on disk
        self._dirty_files: Set[str] = set()
        self._dirty_parts: Set[str] = set()
        # uid -> the copy of its source in the last state taken: states share the sources that didn't change (memory)
        self._frozen_sources: Dict[int, Dict[str, Any]] = {}
        # part object uid -> the copy of its source in the last state taken
        self._frozen_part_sources: Dict[int, Dict[str, Any]] = {}
        # (component key, index) -> the copy of a directive in the last state taken
        self._frozen_directives: Dict[Tuple[str, int], Dict[str, Any]] = {}
        # key -> the state of a file (a part) in the last state taken: states share the files that didn't change
        self._file_states: Dict[str, FileState] = {}
        self._part_states: Dict[str, FileState] = {}

    # --- reading ---

    def is_dirty(self, key: str) -> bool:
        """:return: whether a file or a part (by its key) differs from the file it was loaded from"""
        return key in self._dirty_files or key in self._dirty_parts

    @property
    def dirty_paths(self) -> List[Path]:
        """The files that have changes, of all devices."""
        return [self.files[key].component.path for key in self.files if key in self._dirty_files] + [
            self.parts[key].component.path for key in self.parts if key in self._dirty_parts
        ]

    def changes(self) -> List[ComponentChanges]:
        """:return: what to change in the source files to save the draft, for every file of all devices that has changes"""
        return self.changes_of(self.files, self.parts)

    def changes_of(self, files: Iterable[str], parts: Iterable[str]) -> List[ComponentChanges]:
        """:return: what to change in some of the files (by their keys) to save them, for those that have changes"""
        result = [
            _component_changes(
                self.files[key].component,
                self.files[key].directives,
                [(obj.index, obj.source) for obj in self.files[key].objects],
            )
            for key in files
            # what shows a part on its own is in no file
            if not self.files[key].component.is_scratch
        ]
        result += [
            _component_changes(self.parts[key].component, {}, [(obj.index, obj.source) for obj in self.parts[key].objects])
            for key in parts
        ]
        return [changes for changes in result if changes.changes or changes.removals or changes.deletions or changes.additions]

    # --- for the drafts of the devices (`PlateSession`) ---

    def new_uid(self) -> int:
        """:return: what tells an object of the draft apart, for all devices"""
        return next(self._uids)

    def new_part_uid(self) -> int:
        """:return: what tells a `PartObject` of a part apart"""
        return next(self._part_uids)

    def file_from_disk(self, component: ComponentSource) -> FileDraft:
        """:return: a new draft of a page file as it is in the component (not added to the draft, see `install`)"""
        return FileDraft(
            component=component,
            objects=[
                PartObject(self.new_uid(), index, copy.deepcopy(source))
                for index, source in enumerate(component.sources)
                if not is_directive(source)
            ],
            directives={
                index: copy.deepcopy(source) for index, source in enumerate(component.sources) if is_directive(source)
            },
        )

    def part_from_disk(self, component: ComponentSource) -> PartDraft:
        """:return: a new draft of a part as it is in the component (not added to the draft, see `install`)"""
        return PartDraft(
            component,
            [PartObject(self.new_part_uid(), index, copy.deepcopy(source)) for index, source in enumerate(component.sources)],
        )

    def sessions(self) -> List["PlateSession"]:
        """:return: the drafts of the devices that show files of this draft"""
        alive = [(ref, ref()) for ref in self._sessions]
        self._sessions = [ref for ref, session in alive if session is not None]
        return [session for _ref, session in alive if session is not None]

    def attach(self, session: "PlateSession"):
        """The draft of a device shows files of this draft: it follows their changes from now on."""
        if not any(other is session for other in self.sessions()):
            self._sessions.append(weakref.ref(session))

    def detach(self, session: "PlateSession"):
        self._sessions = [ref for ref in self._sessions if ref() is not session and ref() is not None]

    def install(
        self, session: Optional["PlateSession"], files: Dict[str, FileDraft], parts: Dict[str, PartDraft]
    ) -> Tuple[Set[str], Set[str]]:
        """
        Use these drafts of files and parts from now on (a device was loaded or reverted), and attach the device that shows
        them. The steps of the undo history that changed a file whose draft is replaced are forgotten.
        :return: the keys of the files and of the parts whose drafts were replaced
        """
        replaced_files = {key for key, draft in files.items() if key in self.files and self.files[key] is not draft}
        replaced_parts = {key for key, draft in parts.items() if key in self.parts and self.parts[key] is not draft}
        self.files.update(files)
        self.parts.update(parts)
        if replaced_files or replaced_parts:
            self._forget(replaced_files, replaced_parts)
        self._update_dirty(set(files), set(parts))
        if session is not None:
            self.attach(session)
        return replaced_files, replaced_parts

    def _forget(self, files: Set[str], parts: Set[str]):
        """Forget the undo history of files and parts whose drafts were replaced: their states are not those of the draft."""

        def changes_them(step: Step[DraftState]) -> bool:
            changed_files, changed_parts = step.before.changed(step.after)
            return bool(changed_files & files or changed_parts & parts)

        def without_them(state: DraftState) -> DraftState:
            return DraftState(
                files={key: file for key, file in state.files.items() if key not in files},
                parts={key: part for key, part in state.parts.items() if key not in parts},
            )

        self.history.drop(changes_them)
        self.history = self.history.mapped(without_them)
        for key in files:
            self._file_states.pop(key, None)
        for key in parts:
            self._part_states.pop(key, None)

    def render_again(self, files: Set[str], parts: Set[str], skip: Optional["PlateSession"] = None):
        """Render the other devices that show one of the files or parts again, from the draft (their drafts were replaced)."""
        for session in self.sessions():
            if session is not skip and session.shows(files, parts):
                session._render_again()

    def discard(self, session: "PlateSession"):
        """
        Discard the changes of the files and parts a device shows (also for the other devices that show them), and detach it:
        the files are as they were loaded (or saved) afterwards.
        """
        self.detach(session)
        files = {key: self.file_from_disk(self.files[key].component) for key in session.file_keys}
        parts = {key: self.part_from_disk(self.parts[key].component) for key in session.part_keys}
        replaced_files, replaced_parts = self.install(None, files, parts)
        self.render_again(replaced_files, replaced_parts)

    def state(self) -> DraftState:
        """The sources in it are shared with other states: never change them."""
        return DraftState(
            files={key: self._file_state(key) for key in self.files},
            parts={key: self._part_state(key) for key in self.parts},
        )

    def _file_state(self, key: str) -> FileState:
        draft = self.files[key]
        state = FileState(
            objects=tuple(
                (obj.uid, obj.index, _frozen_source(obj.uid, obj.source, self._frozen_sources)) for obj in draft.objects
            ),
            directives={index: self._frozen_directive(key, index, directive) for index, directive in draft.directives.items()},
        )
        last = self._file_states.get(key)
        if last is not None and last == state:
            return last
        self._file_states[key] = state
        return state

    def _part_state(self, key: str) -> FileState:
        state = FileState(
            objects=tuple(
                (obj.uid, obj.index, _frozen_source(obj.uid, obj.source, self._frozen_part_sources))
                for obj in self.parts[key].objects
            ),
            directives={},
        )
        last = self._part_states.get(key)
        if last is not None and last == state:
            return last
        self._part_states[key] = state
        return state

    def _frozen_directive(self, key: str, index: int, directive: Dict[str, Any]) -> Dict[str, Any]:
        """:return: a copy of a directive of the draft, the one of the last state if it didn't change since"""
        frozen = self._frozen_directives.get((key, index))
        if frozen is None or frozen != directive:
            frozen = copy.deepcopy(directive)
            self._frozen_directives[(key, index)] = frozen
        return frozen

    def edited(self, description: str, before: DraftState, after: DraftState, merge_key: Any):
        """An edit through the draft of a device changed the draft (its objects are in the files already): a step of the history."""
        self.history.push(description, before, after, merge_key)
        self._update_dirty(*before.changed(after))

    def sync_others(self, editor: "PlateSession", before: DraftState, after: DraftState, description: str):
        """The other devices that show a file the edit changed render it again (and tell their listeners)."""
        for session in self.sessions():
            if session is not editor:
                session._sync(before, after, ChangeKind.EDIT, description)

    def undo(self, session: "PlateSession") -> Optional[DraftChange]:
        """:return: what the undo changed for the device (empty if none of its files), None if there was nothing to undo"""
        step = self.history.undo()
        return None if step is None else self._restore(session, step, step.before, ChangeKind.UNDO)

    def redo(self, session: "PlateSession") -> Optional[DraftChange]:
        """:return: what the redo changed for the device (empty if none of its files), None if there was nothing to redo"""
        step = self.history.redo()
        return None if step is None else self._restore(session, step, step.after, ChangeKind.REDO)

    def _restore(self, session: "PlateSession", step: Step[DraftState], state: DraftState, kind: ChangeKind) -> DraftChange:
        """Change the files that a step of the history changed to a state; every device that shows one renders it again."""
        files, parts = step.before.changed(step.after)
        before = self.state()
        for key in files:
            draft = self.files[key]
            draft.objects = _restored_objects(draft.objects, state.files[key].objects)
            draft.directives = {index: copy.deepcopy(directive) for index, directive in state.files[key].directives.items()}
        for key in parts:
            part = self.parts[key]
            part.objects = _restored_objects(part.objects, state.parts[key].objects)
        after = self.state()
        self._update_dirty(files, parts)
        result = None
        for other in self.sessions():
            change = other._sync(before, after, kind, step.description)
            if other is session:
                result = change
        if result is None:
            # the step changed only files that the device doesn't show
            result = DraftChange(kind=kind, description=step.description, objects=[], added=[], removed=False, pages=set())
        return result

    def mark_saved(self, saver: "PlateSession", written: Dict[Path, str]):
        """
        Files of the draft were saved: they have this content now (see `changes`), with the objects of the draft in their
        order. The undo history goes on (see `PlateSession.mark_saved`), and the devices that show the files follow.
        :param saver: the draft of the device that saved them: it tells its listeners in any case
        """
        # component key -> the old index of a kept source -> its new one
        moved: Dict[str, Dict[int, int]] = {}
        # component key -> uid of an object -> its new index
        new_indices: Dict[str, Dict[int, int]] = {}
        for key, draft in self.files.items():
            component = draft.component
            if component.path not in written:
                continue
            # the file keeps its directives and the objects that were not removed in their order, the new ones are at its end
            kept = dict(draft.directives) | {obj.index: obj.source for obj in draft.objects if obj.index is not None}
            moved[key] = {old: new for new, old in enumerate(sorted(kept))}
            added = [obj for obj in draft.objects if obj.index is None]
            new_index = {obj.uid: len(kept) + position for position, obj in enumerate(added)}
            for obj in draft.objects:
                obj.index = moved[key][obj.index] if obj.index is not None else new_index[obj.uid]
            new_indices[key] = {obj.uid: obj.index for obj in draft.objects}
            sources = [kept[old] for old in sorted(kept)] + [obj.source for obj in added]
            draft.component = replace(
                component, content=written[component.path], sources=[copy.deepcopy(source) for source in sources]
            )
            draft.directives = {moved[key][index]: directive for index, directive in draft.directives.items()}
            self._file_states.pop(key, None)
        self._frozen_directives = {}

        # part key -> uid of a part object -> its new index
        part_indices: Dict[str, Dict[int, int]] = {}
        for key, part in self.parts.items():
            if part.component.path not in written:
                continue
            # like a file: the objects that were not removed in their order, then the new ones
            kept_indices = sorted(obj.index for obj in part.objects if obj.index is not None)
            moved_part = {old: new for new, old in enumerate(kept_indices)}
            added = [obj for obj in part.objects if obj.index is None]
            for obj in part.objects:
                obj.index = moved_part[obj.index] if obj.index is not None else len(kept_indices) + added.index(obj)
            part_indices[key] = {obj.uid: obj.index for obj in part.objects}
            part.component = replace(
                part.component,
                content=written[part.component.path],
                sources=[copy.deepcopy(obj.source) for obj in sorted(part.objects, key=lambda obj: obj.index)],
            )
            self._part_states.pop(key, None)

        # the states of the history share the files: each is translated once
        translated: Dict[int, Tuple[FileState, FileState]] = {}

        def translate_file(state: FileState, indices: Dict[int, int], directives: Dict[int, int]) -> FileState:
            if id(state) not in translated:
                translated[id(state)] = (
                    state,
                    FileState(
                        objects=tuple((uid, indices.get(uid), source) for uid, _index, source in state.objects),
                        directives={directives[index]: directive for index, directive in state.directives.items()},
                    ),
                )
            return translated[id(state)][1]

        def translate(state: DraftState) -> DraftState:
            return DraftState(
                files={
                    key: translate_file(file, new_indices[key], moved[key]) if key in moved else file
                    for key, file in state.files.items()
                },
                parts={
                    key: translate_file(part, part_indices[key], {}) if key in part_indices else part
                    for key, part in state.parts.items()
                },
            )

        self.history = self.history.mapped(translate)
        self._update_dirty(set(moved), set(part_indices))
        for session in self.sessions():
            session._saved(moved, set(part_indices), notify=session is saver)

    def _update_dirty(self, files: Iterable[str], parts: Iterable[str]):
        for key in files:
            if key in self.files and _file_differs(self.files[key]):
                self._dirty_files.add(key)
            else:
                self._dirty_files.discard(key)
        for key in parts:
            if key in self.parts and _part_differs(self.parts[key]):
                self._dirty_parts.add(key)
            else:
                self._dirty_parts.discard(key)


def _restored_objects(
    objects: List[PartObject], state: Tuple[Tuple[int, Optional[int], Dict[str, Any]], ...]
) -> List[PartObject]:
    """:return: the objects of a file as they are in a state; those that stay keep their source dict (it is shared)"""
    existing = {obj.uid: obj for obj in objects}
    result = []
    for uid, index, source in state:
        obj = existing.get(uid)
        if obj is None:
            obj = PartObject(uid, index, copy.deepcopy(source))
        elif obj.source != source:
            obj.source.clear()
            obj.source.update(copy.deepcopy(source))
        obj.index = index
        result.append(obj)
    return result


def _frozen_source(uid: int, source: Dict[str, Any], frozen_sources: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """:return: a copy of the source of an object, the one of the last state if the source didn't change since"""
    frozen = frozen_sources.get(uid)
    if frozen is None or frozen != source:
        frozen = copy.deepcopy(source)
        frozen_sources[uid] = frozen
    return frozen


def _file_differs(draft: FileDraft) -> bool:
    component = draft.component
    if component.is_scratch:
        # its vars are not saved
        return False
    if any(directive != component.sources[index] for index, directive in draft.directives.items()):
        return True
    indices = [index for index, source in enumerate(component.sources) if not is_directive(source)]
    return len(draft.objects) != len(indices) or any(
        obj.index != index or obj.source != component.sources[index] for index, obj in zip(indices, draft.objects)
    )


def _part_differs(part: PartDraft) -> bool:
    return [obj.index for obj in part.objects] != list(range(len(part.component.sources))) or any(
        obj.source != source for obj, source in zip(part.objects, part.component.sources)
    )


def _component_changes(
    component: ComponentSource,
    directives: Dict[int, Dict[str, Any]],
    objects: List[Tuple[Optional[int], Dict[str, Any]]],
) -> ComponentChanges:
    """
    :param directives: index in the file -> a directive as the draft has it (they stay where they are)
    :param objects: (index in the file, None for a new one; source) of the other objects of the file, in the order of the
        draft
    """
    component_changes = ComponentChanges(component=component)
    kept: Dict[int, Dict[str, Any]] = dict(directives)
    for index, directive in directives.items():
        removed = set(component.sources[index]) - set(directive)
        if removed:
            component_changes.removals[index] = removed
        changed = {key: value for key, value in directive.items() if component.sources[index].get(key) != value}
        if changed:
            component_changes.changes[index] = copy.deepcopy(changed)
    for index, source in objects:
        if index is None:
            component_changes.additions.append(copy.deepcopy(source))
            continue
        kept[index] = source
        original = component.sources[index]
        removed = set(original) - set(source)
        if removed:
            raise AssertionError(f"Removing properties from a source object is not supported: {removed}")
        changed = {key: value for key, value in source.items() if key not in original or original[key] != value}
        if changed:
            component_changes.changes[index] = copy.deepcopy(changed)

    component_changes.deletions = set(range(len(component.sources))) - set(kept)
    component_changes.expected_sources = [
        copy.deepcopy(kept[index]) for index in range(len(component.sources)) if index in kept
    ] + component_changes.additions
    return component_changes
