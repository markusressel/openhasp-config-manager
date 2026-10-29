"""The data of a draft: what a `PlateSession` is made of and what it reports about its changes."""

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Protocol, Set, Tuple

from openhasp_config_manager.processing.jsonl.includes import Expansion, ObjectOrigin, PartFile
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor

# one `!include` on the way to an included object, as the draft tells it apart: the file with the directive, the directive
# (its index in a file of the draft, the uid of its `PartObject` in a part) and the loop values of the instance (as JSON)
StepKey = Tuple[Path, int, str]


class DraftRenderer(Protocol):
    """
    Renders source objects like a deployment does (see DeviceProcessor), with the template variables of their component.
    """

    def render_object(self, component: str, source: Dict[str, Any], scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """:param scope: the variables of the instance of a part, for an included object (see `ExpandedObject.scope`)"""
        ...

    def expand_objects(self, component: str, sources: List[Dict[str, Any]]) -> Expansion:
        """:return: the objects of a component with its directives (`!include`) replaced by the objects they include"""
        ...

    def set_draft_sources(self, sources: Dict[str, List[Dict[str, Any]]]):
        """
        Templates that refer to other objects (`{{ p1b2.x }}`) see these source objects, per component key: the objects as
        written in the files, with their directives.
        """
        ...

    def set_draft_parts(self, parts: Dict[Path, PartFile]):
        """The `!include`s include these parts instead of their files (the parts as the draft has them)."""
        ...

    def part_source(self, path: Path) -> "ComponentSource":
        """:return: a part (the path of an included object's origin) as it is on disk, its key is its path"""
        ...

    def referenced_objects(
        self, component: str, source: Dict[str, Any], page: Any = None, scope: Optional[Dict[str, Any]] = None
    ) -> Set[str]:
        """:return: the objects (`p1b2`) the templates of a source object refer to, `ANY_OBJECT` if that can't be told"""
        ...

    def check_template(
        self, component: str, template: str, name: Optional[str] = None, scope: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """:return: why the template can't be rendered (in the object `name`, for `this` and `bY`), or None if it can"""
        ...

    def template_suggestions(self, component: str, scope: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Any]]:
        """
        :param scope: the variables of the instance of a part, for an included object
        :return: (template, its current value) for the variables available in the component
        """
        ...

    def variable_value(self, component: str, name: str) -> Any:
        """:return: the value of a template variable in the component :raises KeyError: if it has none"""
        ...

    def render_text(self, component: str, text: str) -> str:
        """:return: a text with templates, rendered like a deployment does :raises jinja2.TemplateError: if it can't be"""
        ...

    def path_variable_value(self, path: Path, name: str) -> Any:
        """:return: the value of a variable for a file that has no objects in the draft :raises KeyError: if it has none"""
        ...

    def render_path_text(self, path: Path, text: str) -> str:
        """:return: a text with templates, rendered with the variables of a file that has no objects in the draft"""
        ...


@dataclass(frozen=True)
class ComponentSource:
    """A jsonl component of the draft, as it was read from disk."""

    # the key of the component in the draft
    key: str
    path: Path
    # the content of the file when it was loaded, to detect changes on disk
    content: str
    # whether it is a component of the common folder, shared by all devices
    is_common: bool
    # the objects as written in the file (templates not rendered), in the order of the file
    sources: List[Dict[str, Any]]


@dataclass
class DraftEntry:
    component: str
    # the index of the object in the source file, None for objects added in the draft
    index: Optional[int]
    # the object as written in the source file (with templates), changed by the draft
    source: Dict[str, Any]
    # tells the object apart in the undo history: the rendered dict of an object is a new one after its removal is undone
    uid: int
    # for an object that an `!include` of the file includes: where it is written (`index` is the one of the outermost
    # directive then, and `source` is the object of the part, which the draft doesn't change)
    origin: Optional[ObjectOrigin] = None
    # the variables of the instance of the part, for an included object
    scope: Optional[Dict[str, Any]] = None
    # what tells an included object apart, also after its part or its directives changed: the `!include`s on the way to it
    # and the uid of its `PartObject`
    instance: Optional[Tuple[Tuple[StepKey, ...], int]] = None

    @property
    def is_included(self) -> bool:
        return self.origin is not None


@dataclass
class PartObject:
    """An object of a part (or an `!include` in it) in the draft: the included objects of all its instances share it."""

    # tells it apart while its index changes
    uid: int
    # the index in the part file, None for an object added in the draft
    index: Optional[int]
    # as written in the part, with its templates, changed by the draft
    source: Dict[str, Any]


@dataclass
class PartDraft:
    """A part that the files of the draft include, with its objects as the draft has them."""

    # the part as read from disk (its key is its path)
    component: ComponentSource
    objects: List[PartObject]

    def part_file(self) -> PartFile:
        """:return: the part for the expansion (see `DraftRenderer.set_draft_parts`)"""
        editor = _source_editor(self.component.content)
        return PartFile(
            path=self.component.path,
            content=self.component.content,
            sources=[obj.source for obj in self.objects],
            lines=tuple(None if obj.index is None else editor.line_of(obj.index) for obj in self.objects),
        )


@lru_cache(maxsize=64)
def _source_editor(content: str) -> JsonlSourceEditor:
    return JsonlSourceEditor(content)


@dataclass(frozen=True)
class PartInstance:
    """One instance of a part in the draft: the `!include`s that lead to it (the last one includes the part)."""

    part: Path
    steps: Tuple[StepKey, ...]


class DraftItem(NamedTuple):
    """An object of the draft in an undo state, see `DraftEntry`."""

    uid: int
    index: Optional[int]
    # None for an included object: its source is the one of its `PartObject` in the state
    source: Optional[Dict[str, Any]]
    origin: Optional[ObjectOrigin]
    scope: Optional[Dict[str, Any]]
    instance: Optional[Tuple[Tuple[StepKey, ...], int]]


@dataclass(frozen=True)
class DraftState:
    """The draft, for undo. The sources in it are shared with other states: never change them."""

    # per component key: its objects, in order
    objects: Dict[str, Tuple[DraftItem, ...]]
    # per component key: the index of a directive (`!include`) in the source file -> the directive as the draft has it
    directives: Dict[str, Dict[int, Dict[str, Any]]]
    # per part key: (uid, index in the part file, source) of its objects, in order
    parts: Dict[str, Tuple[Tuple[int, Optional[int], Dict[str, Any]], ...]] = field(default_factory=dict)


class ChangeKind(Enum):
    EDIT = "edit"
    UNDO = "undo"
    REDO = "redo"
    # the draft was saved: nothing changed but whether it has changes
    SAVE = "save"


@dataclass(frozen=True)
class DraftChange:
    """
    What a finished edit, undo or redo changed in the draft. Objects with templates that refer to the changed ones may have
    changed too (they are rendered again).
    """

    kind: ChangeKind
    # the edit that was made, undone or redone, e.g. "Move p1b2"
    description: str
    # the rendered objects whose source changed, or that were added, in the order of the draft
    objects: List[Dict]
    # the rendered objects that were added (also in `objects`)
    added: List[Dict]
    # whether objects were removed
    removed: bool
    # the pages of the changed and added objects; for an undo or redo also of the removed ones and where objects were before
    pages: Set[Any]
    # the objects to select afterwards instead of the added ones, e.g. the object whose `!include` was changed (empty if it
    # is gone); None selects the added ones
    selected: Optional[List[Dict]] = None

    @property
    def adds_or_removes(self) -> bool:
        return bool(self.added) or self.removed


@dataclass
class ComponentChanges:
    component: ComponentSource
    # index in the source file -> properties to set
    changes: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    deletions: Set[int] = field(default_factory=set)
    additions: List[Dict[str, Any]] = field(default_factory=list)
    # the source objects the file must have after the changes
    expected_sources: List[Dict[str, Any]] = field(default_factory=list)
