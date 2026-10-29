"""The data of a draft: what a `PlateSession` is made of and what it reports about its changes."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

from openhasp_config_manager.processing.jsonl.includes import Expansion, ObjectOrigin


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

    def template_suggestions(self, component: str) -> List[Tuple[str, Any]]:
        """:return: (template, its current value) for the variables available in the component"""
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

    @property
    def is_included(self) -> bool:
        return self.origin is not None


# the objects of the draft, for undo: per component key (uid, index in the source file, source) of its objects, in order
DraftState = Dict[str, Tuple[Tuple[int, Optional[int], Dict[str, Any]], ...]]


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
