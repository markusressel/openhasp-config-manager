import copy
import json
import logging
import re
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Optional, Any, Set, Tuple, Hashable, Iterator, Callable, NamedTuple, Iterable, FrozenSet

from jinja2 import TemplateError

from openhasp_config_manager.gui.domain.draft.config_draft import (
    ConfigDraft,
    FileDraft,
    HistoryStep,
    UndoRefusedError,
    with_directives,
)
from openhasp_config_manager.gui.domain.draft.edit_history import BlockedStepError
from openhasp_config_manager.gui.domain.draft.model import (
    ChangeKind,
    ComponentChanges,
    ComponentSource,
    DraftChange,
    DraftEntry,
    DraftRenderer,
    DraftState,
    PartDraft,
    PartInstance,
    PartObject,
    StepKey,
)
from openhasp_config_manager.gui.domain.draft.page_objects import next_free_id
from openhasp_config_manager.gui.domain.draft.part_ids import new_part_object_ids
from openhasp_config_manager.gui.domain.file_tree import config_root_of
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl.includes import (
    FOR,
    INCLUDE,
    INCLUDE_KEYS,
    VARS,
    ExpandedObject,
    describe_step,
    IncludeError,
    IncludeStep,
    ObjectOrigin,
    describe_includes,
    directive_error,
    display_path,
    is_directive,
)
from openhasp_config_manager.processing.template_rendering import THIS, has_nested_templates, referenced_objects
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor, is_numeric_property
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor

if TYPE_CHECKING:
    from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus

LOGGER = logging.getLogger(__name__)

# stands for every object: the objects a template refers to can't be told
ANY_OBJECT = "*"
# the object itself in its templates
_THIS = re.compile(rf"\b{THIS}\b")


class _Rendered(NamedTuple):
    """A draft rendered from the drafts of its files (see `PlateSession._render_from_disk`)."""

    working_objects: OrderedDict[str, List[Dict]]
    # by id of the rendered object
    entries: Dict[int, DraftEntry]
    # component key -> the errors of its directives
    include_errors: Dict[str, List[IncludeError]]


class _Reincluded(NamedTuple):
    """What including the directives again changed (see `PlateSession._reinclude`)."""

    # the names (before and after) of the objects that were added, removed or rendered again
    names: Set[str]
    # the objects that were added or rendered again
    rendered: List[Dict]
    # the objects that were added (also in `rendered`)
    added: List[Dict]
    # the objects that were removed
    removed: List[Dict]
    # the pages of these objects, before and after
    pages: Set[Any]


class ReadOnlyObjectError(ValueError):
    """An object of the draft can't be changed: it is included by an `!include` (the message says from where)."""


class InvalidDirectiveError(ValueError):
    """A change of an `!include` can't be made: the directive would have an error (the message says which)."""


@lru_cache(maxsize=64)
def _source_editor(content: str) -> JsonlSourceEditor:
    # the text of a component is parsed once, not for every object asked about
    return JsonlSourceEditor(content)


class PlateSession:
    """
    The draft of a device's pages (of one cmd component) during an app session: how the device sees the files of a
    `ConfigDraft`, which several devices share.

    The draft keeps every object twice: rendered (`working_objects`, shown in the preview) and as written in its source
    file, with templates. Edits change the source and render the object again, so the draft can be saved back into the
    source files without losing templates (see `changes()`). The sources are those of the `ConfigDraft`: an edit of a file
    that another device shows too (a common file, a part) is seen there (it renders the file again). The rendered objects
    are per device, because a device renders a shared object with its own variables.

    The directives of a file (`!include`) are replaced by the objects they include. Those are shown like the others, but are
    read-only: they are written in another file (the part), once for all of its instances. The `vars` and `for` of a directive
    can be changed (`set_directive_value`): its objects are included again. Saving writes the directives only where they
    changed.

    The draft keeps the parts too (`PartDraft`): the included objects of all instances of a part object share its source. In
    part mode the objects of one instance of a part can be changed like the objects of a file; every instance follows, and
    saving writes the part. Part mode belongs to a view of the draft, not to the draft (see `PartFocus`): the methods that
    depend on it take the instance (`part_instance`), None for the objects of the files.
    """

    def __init__(self, device: Device, config: Optional[ConfigDraft] = None):
        """:param config: the files of the config directory as the draft has them, shared with other devices (a new one by default)"""
        self.device = device
        self._config = ConfigDraft() if config is None else config
        # the keys of the components whose objects the device shows, in the order of the deployment
        self._keys: List[str] = []
        self._renderer: Optional[DraftRenderer] = None
        self._working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        # id(rendered object) -> its source
        self._entries: Dict[int, DraftEntry] = {}
        self._loaded = False
        # the edit that is running (see `edit`): its description, merge key, the state before it and the included objects then
        self._edit: Optional[Tuple[str, Optional[Hashable], DraftState, Dict[int, Tuple[int, Any]]]] = None
        self._listeners: List[Callable[[DraftChange], None]] = []
        # component key -> the errors of its directives, when it was loaded
        self._include_errors: Dict[str, List[IncludeError]] = {}
        # the objects to select after the running edit (see `DraftChange.selected`)
        self._selected_after_edit: Optional[List[Dict]] = None
        # the last expansion of a changed directive (see `_expand_directive`): its key, and the result
        self._last_expansion: Optional[Tuple[Tuple[str, int, str], Tuple[List[ExpandedObject], List[str]]]] = None
        # part key (its path as the origins of the included objects have it) -> the part (of the `ConfigDraft`) that the
        # files of the device include
        self._parts: OrderedDict[str, PartDraft] = OrderedDict()
        # the part modes of the views of the draft, whose instances it keeps up to date (see `PartFocus`)
        self._part_focuses: List["PartFocus"] = []

        # when the draft was read from the files on disk the last time (loaded, reverted)
        self.loaded_at: Optional[datetime] = None

    @property
    def config(self) -> ConfigDraft:
        """The files of the config directory as the draft has them, shared with the drafts of other devices."""
        return self._config

    def load(self, components: List[ComponentSource], renderer: DraftRenderer):
        """
        Initializes the draft from the components as they are on disk. A file (or part) that the `ConfigDraft` has already is
        taken from there if it has changes or didn't change on disk; otherwise it is loaded again, and the other devices that
        show it render it again. If they can't be rendered, this raises and the draft stays as it was. Part mode (of each
        `PartFocus`) goes on in the instance that is included at the same place, if there is one (see `reset_to_disk`).
        """
        described = self._described_part_focuses() if self._loaded else [(focus, None) for focus in self._part_focuses]
        rendered, files, parts = self._render_from_disk(components, renderer, False)
        self._renderer = renderer
        self._keys = list(files)
        self._install(rendered, files, parts)
        self._loaded = True
        self._continue_part_focuses(described)

    def reset_to_disk(self):
        """
        Discards all changes of the files of the draft and their undo history, also for the other devices that show them.
        The rendered objects are new objects afterwards. Part mode (of each `PartFocus`) goes on in the instance that is
        included at the same place, if there is one. If the files can't be rendered, this raises and the draft stays as it was.
        """
        # the uids of the parts are new afterwards
        described = self._described_part_focuses()
        try:
            rendered, files, parts = self._render_from_disk(self.components, self._renderer, True)
        except Exception:
            # the renderer sees the objects and parts of the draft again
            self._set_draft_sources()
            raise
        self._install(rendered, files, parts)
        self._continue_part_focuses(described)

    def discard(self):
        """
        Discards all changes of the files of the draft (also for the other devices that show them), and leaves the
        `ConfigDraft`: the draft is not used anymore (e.g. it is loaded anew from disk).
        """
        self._config.discard(self)
        self._loaded = False

    def _render_again(self):
        """
        The `ConfigDraft` has new drafts of files the device shows (another device loaded or reverted them): render the
        device again from it, like `load`. If that fails, the draft is not loaded anymore (see `is_loaded`), and doesn't
        follow the `ConfigDraft` until it is loaded again.
        """
        try:
            described = self._described_part_focuses()
            rendered, files, parts = self._render_from_disk(self.components, self._renderer, False, False)
        except Exception:
            LOGGER.exception(f"Could not render {self.device.name if self.device else 'the draft'} again")
            self._config.detach(self)
            self._loaded = False
            return
        self._install(rendered, files, parts)
        self._continue_part_focuses(described)

    def _install(self, rendered: "_Rendered", files: Dict[str, FileDraft], parts: Dict[str, PartDraft]):
        replaced = self._config.install(self, files, parts)
        self._replace_with(rendered, parts)
        self._config.render_again(*replaced, skip=self)

    def _described_part_focuses(self) -> List[Tuple["PartFocus", Optional[str]]]:
        """:return: each `PartFocus` with where its instance is included (see `describe_instance`), None if it has no objects"""
        return [
            (focus, self.describe_instance(focus.instance))
            if focus.instance is not None and self._objects_of_instance(focus.instance)
            else (focus, None)
            for focus in self._part_focuses
        ]

    def _continue_part_focuses(self, described: List[Tuple["PartFocus", Optional[str]]]):
        """
        After the draft was rendered again: the part mode of each `PartFocus` goes on in the instance that is included at the
        same place as before (described), if there is one; otherwise it ends (its instance is None).
        """
        for focus, description in described:
            focus.instance = (
                None
                if description is None
                else next(
                    (
                        instance
                        for instance in self.part_instances(focus.instance.part)
                        if self.describe_instance(instance) == description
                    ),
                    None,
                )
            )

    def _render_from_disk(
        self, components: List[ComponentSource], renderer: DraftRenderer, fresh: bool, refresh_parts: bool = True
    ) -> Tuple["_Rendered", OrderedDict[str, FileDraft], OrderedDict[str, PartDraft]]:
        """
        Render the components with the drafts of their files: those of the `ConfigDraft`, unless they are new, or have no
        changes and are different on disk (in the components, for the parts as the renderer reads them). Nothing of the
        session or the `ConfigDraft` is changed, except for the renderer.
        :param fresh: all files and parts as they are on disk, also those with changes
        :param refresh_parts: the parts without changes that the `ConfigDraft` has as they are on disk too
        :return: the rendered draft, and the drafts of its files and parts
        """
        config = self._config
        files: OrderedDict[str, FileDraft] = OrderedDict()
        for component in components:
            existing = config.files.get(component.key)
            keep = existing is not None and (existing.component.content == component.content or config.is_dirty(component.key))
            files[component.key] = existing if keep and not fresh else config.file_from_disk(component)
        layouts = {key: draft.indexed_sources() for key, draft in files.items()}
        sources = {key: [source for _index, source, _obj in layout] for key, layout in layouts.items()}
        working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        entries: Dict[int, DraftEntry] = {}
        include_errors: Dict[str, List[IncludeError]] = {}
        parts: OrderedDict[str, PartDraft] = OrderedDict()
        # the parts with changes include what the draft has
        renderer.set_draft_parts(
            {}
            if fresh
            else {
                Path(key): part.part_file() for key, part in config.parts.items() if config.is_dirty(key) or not refresh_parts
            }
        )
        renderer.set_draft_sources(sources)
        expansions = {key: renderer.expand_objects(key, sources[key]) for key in files}
        # the parts the files include, also those that only have directives
        for expansion in expansions.values():
            for expanded in expansion.objects:
                for file in [expanded.origin.file, *(step.file for step in expanded.origin.includes[1:])]:
                    if expanded.origin.is_included and str(file) not in parts:
                        parts[str(file)] = self._load_part(renderer, file, fresh, refresh_parts)
        # from now on the expansions include the parts of the draft, whose objects the included objects share
        renderer.set_draft_parts({Path(key): part.part_file() for key, part in parts.items()})
        for key, draft in files.items():
            layout = layouts[key]
            expansion = renderer.expand_objects(key, sources[key])
            include_errors[key] = expansion.errors
            lines = _source_editor(draft.component.content)
            objects = []
            for expanded in expansion.objects:
                origin = expanded.origin
                if origin.is_included:
                    # the expansion has the place of the directive in the objects of the draft, which can differ from the file
                    index = layout[origin.includes[0].index][0]
                    origin = _moved_origin(origin, index, lines.line_of(index))
                    instance = _instance_key(origin, index, parts)
                    entry = DraftEntry(
                        key,
                        index,
                        _part_object(parts, origin.file, instance[1]).source,
                        config.new_uid(),
                        origin=origin,
                        scope=expanded.scope,
                        instance=instance,
                    )
                else:
                    obj = layout[origin.index][2]
                    entry = DraftEntry(key, obj.index, obj.source, obj.uid)
                rendered = renderer.render_object(entry.component, entry.source, entry.scope)
                entries[id(rendered)] = entry
                objects.append(rendered)
            working_objects[key] = objects
        return _Rendered(working_objects, entries, include_errors), files, parts

    def _replace_with(self, rendered: "_Rendered", parts: OrderedDict[str, PartDraft]):
        self._working_objects, self._entries, self._include_errors = rendered
        self._parts = parts
        self._last_expansion = None
        self.loaded_at = datetime.now(timezone.utc)

    @property
    def file_keys(self) -> List[str]:
        """The keys of the components (page files) the device shows."""
        return list(self._keys)

    @property
    def part_keys(self) -> List[str]:
        """The keys of the parts the files of the device include."""
        return list(self._parts)

    def shows(self, files: Set[str], parts: Set[str]) -> bool:
        """:return: whether the device shows one of the files or parts (by their keys)"""
        return any(key in files for key in self._keys) or any(key in parts for key in self._parts)

    @property
    def is_part_alone(self) -> bool:
        """Whether the draft shows a part on its own (see `load_part_alone`), not the pages of a device."""
        return any(component.is_scratch for component in self.components)

    @property
    def is_dirty(self) -> bool:
        """Whether a file the draft shows differs from the file it was loaded from (also by an edit of another device)."""
        return any(self._config.is_dirty(key) for key in self._keys) or any(self._config.is_dirty(key) for key in self._parts)

    @property
    def is_loaded(self) -> bool:
        """Whether the draft was loaded from disk (an empty draft can be loaded too)."""
        return self._loaded

    @property
    def working_objects(self) -> OrderedDict[str, List[Dict]]:
        """The rendered objects per component. Change them only through the methods of the session."""
        return self._working_objects

    @property
    def components(self) -> List[ComponentSource]:
        return [self._file(key).component for key in self._keys]

    # --- reading ---

    def source_of(self, obj: Dict) -> Dict[str, Any]:
        """:return: the object as written in its source file (do not change it)"""
        return self._entry(obj).source

    def component_of(self, obj: Dict) -> ComponentSource:
        return self._file(self._entry(obj).component).component

    def source_index(self, obj: Dict) -> Optional[int]:
        """:return: the index of the object in its source file, None for an object added in the draft"""
        return self._entry(obj).index

    def line_of(self, obj: Dict) -> Optional[int]:
        """
        :return: the line (starting at 1) on which the object starts in its source file, None for an object added in the draft.
            The line of the `!include` for an included object (see `origin_of` for where it is written).
        """
        index = self.source_index(obj)
        return None if index is None else _source_editor(self.component_of(obj).content).line_of(index)

    def is_included(self, obj: Dict) -> bool:
        """:return: whether an `!include` includes the object: it is read-only (see `read_only_reason`)"""
        return self._entry(obj).is_included

    def origin_of(self, obj: Dict) -> Optional[ObjectOrigin]:
        """:return: where an included object is written, and the `!include`s that lead to it; None for the other objects"""
        return self._entry(obj).origin

    def read_only_reason(self, obj: Dict, part_instance: Optional[PartInstance] = None) -> Optional[str]:
        """
        :param part_instance: the instance of a part that is edited in part mode (see `PartFocus`), None outside of part mode
        :return: why the object can't be changed in the draft, None if it can. In part mode only the objects of the part in the
            instance that is edited can be changed.
        """
        entry = self._entry(obj)
        origin = entry.origin
        mode = part_instance
        if mode is None and origin is None:
            return None
        config_dir = config_root_of(self.device.path)
        if mode is not None:
            if self._in_part_mode(entry, mode):
                return None
            part = display_path(mode.part, config_dir)
            if self.is_selectable(obj, mode):
                inner = f"{display_path(origin.file, config_dir)}:{origin.line}"
                return f"It is included from {inner}, by an {INCLUDE} inside of the part {part}: edit that part."
            return f"In part mode only the objects of the part {part} (of the instance that is shown) can be changed."
        part = f"{display_path(origin.file, config_dir)}:{origin.line}"
        return (
            f"It is included from {part} ({describe_includes(origin.includes, config_dir)}). Change it in that file, or the "
            f"vars of the {INCLUDE}."
        )

    # --- part mode ---

    def part_instances(self, part: Path) -> List[PartInstance]:
        """:return: the instances of a part (the path in any spelling) in the files of the draft, in the order of the draft"""
        resolved = Path(part).resolve()
        result: List[PartInstance] = []
        for obj in self._all_objects():
            instance = self._instance_of_part(self._entry(obj), resolved)
            if instance is not None and instance not in result:
                result.append(instance)
        return result

    def instance_of(self, obj: Dict, part: Optional[Path] = None) -> PartInstance:
        """
        :param part: a part on the way to the object, by default the part it is written in
        :return: the instance of the part that the included object belongs to
        :raises ValueError: if the object is not included from that part
        """
        entry = self._entry(obj)
        instance = None
        if entry.is_included:
            instance = self._instance_of_part(entry, Path(part or entry.origin.file).resolve())
        if instance is None:
            raise ValueError(f"{object_name(obj)} is not included from {part or 'a part'}")
        return instance

    def check_part_instance(self, instance: PartInstance):
        """
        Check that the objects of a part can be edited in one of its instances (part mode, see `PartFocus`).
        :raises ValueError: if the instance is not in the draft, or the part is also a file of the draft
        """
        if instance not in self.part_instances(instance.part):
            raise ValueError(f"{instance.part} has no such instance in the draft")
        if self.component_at(instance.part) is not None:
            raise ValueError(
                f"{instance.part.name} is also a page file of the device: change its objects there, not as a part"
            )

    def add_part_focus(self, focus: "PartFocus"):
        """Keep the instance of the part mode of a view up to date (see `PartFocus`), until `remove_part_focus`."""
        self._part_focuses.append(focus)

    def remove_part_focus(self, focus: "PartFocus"):
        self._part_focuses.remove(focus)

    def part_source(self, part: Path) -> ComponentSource:
        """:return: a part of the draft (the path in any spelling) as it was read from disk"""
        return self._part_at(part).component

    def is_selectable(self, obj: Dict, part_instance: Optional[PartInstance] = None) -> bool:
        """
        :param part_instance: the instance of a part that is edited in part mode, None outside of part mode
        :return: whether the object can be selected: in part mode only the objects of the instance that is edited
        """
        mode = part_instance
        if mode is None:
            return True
        entry = self._entry(obj)
        return entry.is_included and self._instance_of_part(entry, mode.part.resolve()) == mode

    def describe_instance(self, instance: PartInstance) -> str:
        """
        :return: where an instance of a part is included, e.g. "devices/plate/page.jsonl:4 (id=20)", outermost first
        :raises StopIteration: if it is not in the draft
        """
        origin = self._entry(self._objects_of_instance(instance)[0]).origin
        config_dir = config_root_of(self.device.path)
        return " > ".join(describe_step(step, config_dir) for step in origin.includes[: len(instance.steps)])

    def page_of_instance(self, instance: PartInstance) -> Any:
        """:return: the page of the first object of an instance of a part :raises IndexError: if it is not in the draft"""
        return self._objects_of_instance(instance)[0].get("page")

    def objects_of_instance(self, instance: PartInstance) -> List[Dict]:
        """:return: the rendered objects of an instance of a part, also those of the parts it includes"""
        return self._objects_of_instance(instance)

    def directive_of(self, obj: Dict) -> Dict[str, Any]:
        """
        :return: the outermost `!include` of an included object (the one in the file of the draft, see `line_of`), as the draft
            has it (do not change it)
        :raises ValueError: for an object that is not included
        """
        entry = self._entry(obj)
        if not entry.is_included:
            raise ValueError(f"{object_name(obj)} is not included by an {INCLUDE}")
        return self._file(entry.component).directives[entry.index]

    def include_errors(self) -> Dict[str, List[IncludeError]]:
        """:return: component key -> what is wrong with the directives of its file (as loaded from disk)"""
        return self._include_errors

    def component_at(self, path: Path) -> Optional[ComponentSource]:
        """:return: the component of a file (the path in any spelling), None if the draft has no objects of that file"""
        resolved = path.resolve()
        return next((component for component in self.components if component.path.resolve() == resolved), None)

    def objects_of_file(self, path: Path) -> Optional[List[Dict]]:
        """:return: the rendered objects of a file of the draft, in the order of the file; None if the draft has none of that file"""
        component = self.component_at(path)
        return None if component is None else list(self._working_objects.get(component.key, []))

    def object_of_source(self, component: str, index: int) -> Optional[Dict]:
        """
        :return: the rendered object that was written as the n-th object of a component's file, None if it was deleted (or the
            n-th object is a directive)
        """
        return next(
            (
                obj
                for obj in self._working_objects.get(component, [])
                if self._entry(obj).index == index and not self._entry(obj).is_included
            ),
            None,
        )

    def is_template(self, obj: Dict, key: str) -> bool:
        value = self.source_of(obj).get(key)
        return isinstance(value, str) and "{{" in value

    def is_percentage(self, obj: Dict, key: str) -> bool:
        """Whether the source has a percentage of the screen size (e.g. "15%") for x, y, w or h."""
        value = self.source_of(obj).get(key)
        return isinstance(value, str) and ObjectDimensionsProcessor.PERCENTAGE_REGEX_PATTERN.match(value) is not None

    def has_computed_position(self, obj: Dict) -> bool:
        """Whether x or y is a template or a percentage: moving the object would replace them with pixels."""
        return any(self.is_template(obj, key) or self.is_percentage(obj, key) for key in ("x", "y"))

    def check_template(self, obj: Dict, template: str) -> Optional[str]:
        """:return: why a template can't be rendered in a property of the object (`this` is the object), None if it can"""
        entry = self._entry(obj)
        return self._renderer.check_template(entry.component, template, object_name(obj), entry.scope)

    def template_suggestions(self, obj: Dict) -> List[Tuple[str, Any]]:
        """:return: (template, its value) for the variables the templates of the object can use, with those of its instance"""
        entry = self._entry(obj)
        return self._renderer.template_suggestions(entry.component, entry.scope)

    def variable_value(self, component: str, name: str) -> Any:
        """:return: the value of a template variable in a component of the draft :raises KeyError: if it has none"""
        return self._renderer.variable_value(component, name)

    def render_text(self, component: str, text: str) -> str:
        """:return: a text with templates (e.g. one template), rendered with the variables of a component of the draft"""
        return self._renderer.render_text(component, text)

    def variable_value_at(self, path: Path, name: str) -> Any:
        """
        :return: the value of a template variable in a file: of its component if it has objects in the draft, else the variables
            of the YAML files the device sees there (e.g. in a variable file) :raises KeyError: if it has none
        """
        component = self.component_at(path)
        if component is not None:
            return self.variable_value(component.key, name)
        return self._renderer.path_variable_value(path, name)

    def render_text_at(self, path: Path, text: str) -> str:
        """:return: a text with templates, rendered like `variable_value_at` finds the variables of a file"""
        component = self.component_at(path)
        if component is not None:
            return self.render_text(component.key, text)
        return self._renderer.render_path_text(path, text)

    def variable_names(self, component: str) -> List[str]:
        """:return: the names of the template variables a file can use, e.g. "theme.navbar.height" """
        return [template[3:-3] for template, _value in self._renderer.template_suggestions(component)]

    # --- editing ---

    def check_value(self, obj: Dict, key: str, value: Any, part_instance: Optional[PartInstance] = None) -> Optional[str]:
        """
        Check a value for a property, as written in the source (a literal or a template), before setting it.
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :return: why it can't be set, or None if it can
        """
        reason = self.read_only_reason(obj, part_instance)
        if reason is not None:
            return reason
        try:
            rendered = self._render_with(obj, key, value)
        except TemplateError as ex:
            return f"Invalid template: {ex.message}"
        result = rendered.get(key)
        if is_numeric_property(key) and not isinstance(result, (int, float)):
            return f"Must be a number, renders to {result!r}."
        return None

    def set_source_value(self, obj: Dict, key: str, value: Any, part_instance: Optional[PartInstance] = None):
        """
        Set a property as it is written in the source, a literal or a template, and render the object again.
        Nothing changes if the object can't be rendered with it (see check_value).
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :raises ReadOnlyObjectError: for an included object (outside of the instance of part mode)
        """
        self._check_editable(obj, part_instance)
        before = object_name(obj)
        rendered = self._render_with(obj, key, value)
        with self.edit(f"Change {key} of {before}"):
            entry = self._entry(obj)
            entry.source[key] = value
            if entry.is_included:
                # the object of the part: every instance follows
                self._reinclude_and_render({str(entry.origin.file)})
                return
            self._apply(obj, rendered)
            self._render_dependents(obj, before)

    def check_directive_value(self, obj: Dict, key: str, value: Dict[str, Any]) -> Optional[str]:
        """
        Check a new `vars` or `for` for the outermost `!include` of an included object, before setting it: the directive is
        included again with it.
        :return: what would be wrong (an error of the directive, an id collision, too many instances, ...), None if nothing
        """
        entry = self._entry(obj)
        directive = self._changed_directive(obj, key, value)
        error = directive_error(directive)
        if error is not None:
            return error
        _objects, errors = self._expand_directive(entry.component, entry.index, directive)
        return "\n".join(errors) if errors else None

    def set_directive_value(self, obj: Dict, key: str, value: Dict[str, Any]):
        """
        Set the `vars` or `for` of the outermost `!include` of an included object (the whole mapping, as written in the file:
        values or templates; names can be added and removed, an empty mapping removes the key), and include its part again:
        objects of its instances that stay keep their rendered dict (and are rendered again), the others are added or
        removed. The object stays selected if it is still included, otherwise the object that takes its place when a name
        of `for` was added or removed (see `_successor`).
        :raises InvalidDirectiveError: if the directive would have an error (see `check_directive_value`); nothing changes then
        """
        error = self.check_directive_value(obj, key, value)
        if error is not None:
            raise InvalidDirectiveError(error)
        entry = self._entry(obj)
        loop = dict(entry.origin.includes[0].loop)
        with self.edit(f"Change {key} of the {INCLUDE} at line {self.line_of(obj)}"):
            self._file(entry.component).directives[entry.index] = self._changed_directive(obj, key, value)
            self._reinclude_and_render(set())
            successor = obj if id(obj) in self._entries else self._successor(entry, loop)
            self._selected_after_edit = [] if successor is None else [successor]

    def _successor(self, before: DraftEntry, loop: Dict[str, Any]) -> Optional[Dict]:
        """
        :param before: an included object that is gone after its `!include` changed
        :param loop: the loop variables of its instance
        :return: the object of the same part object in the first instance whose loop variables agree with these on the names
            both have (a name of `for` was added or removed), None if there is none
        """
        (_file, index, _loop), *inner = before.instance[0]
        for obj in self._working_objects[before.component]:
            entry = self._entry(obj)
            if not entry.is_included or entry.instance[1] != before.instance[1]:
                continue
            (_file, other_index, _loop), *other_inner = entry.instance[0]
            other_loop = entry.origin.includes[0].loop
            if (other_index, other_inner) == (index, inner) and all(
                other_loop[name] == loop[name] for name in other_loop.keys() & loop.keys()
            ):
                return obj
        return None

    def computed_position_reasons(self, obj: Dict, max_length: int = 40) -> List[str]:
        """:return: why the position is computed, e.g. ["x is a template: {{ nav.x }}", "y is a percentage: 15%"]"""
        result = []
        for key in ("x", "y"):
            value = str(self.source_of(obj).get(key))
            if len(value) > max_length:
                value = value[: max_length - 1] + "…"
            if self.is_template(obj, key):
                result.append(f"{key} is a template: {value}")
            elif self.is_percentage(obj, key):
                result.append(f"{key} is a percentage: {value}")
        return result

    def use_pixel_position(self, obj: Dict, part_instance: Optional[PartInstance] = None):
        """Replace a template or a percentage in x and y with the pixels it renders to, so the object can be moved."""
        self._check_editable(obj, part_instance)
        with self.edit(f"Use pixels for x/y of {object_name(obj)}"):
            for key in ("x", "y"):
                if self.is_template(obj, key) or self.is_percentage(obj, key):
                    self.set_source_value(obj, key, obj.get(key, 0), part_instance)

    def remove_source_value(self, obj: Dict, key: str, part_instance: Optional[PartInstance] = None):
        """
        Remove a property the draft added to the source (e.g. resetting a theme default that was changed),
        and render the object again.
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        """
        self._check_editable(obj, part_instance)
        before = object_name(obj)
        with self.edit(f"Reset {key} of {before}"):
            entry = self._entry(obj)
            entry.source.pop(key)
            if entry.is_included:
                self._reinclude_and_render({str(entry.origin.file)})
                return
            self._render(obj)
            self._render_dependents(obj, before)

    def add_object(
        self, component: str, source: Dict[str, Any], part_instance: Optional[PartInstance] = None
    ) -> Optional[Dict]:
        """
        Add an object to the end of a component (it is drawn on top, and saved to the end of the file).
        :param component: a component key, or in part mode the key of the part (`PartInstance.part`): the object is added to
            every instance then, with templates for its page and id (see `new_part_object_ids`)
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :return: the rendered object (in part mode: in the instance that is edited, None if it can't be included there)
        :raises ReadOnlyObjectError: for a part outside of its part mode
        """
        if component in self._parts:
            return self._add_part_object(component, source, part_instance)
        with self.edit(f"Add {source.get('obj', 'object')}"):
            obj = self._create(component, None, copy.deepcopy(source))
            self._working_objects[component].append(obj)
            self._render_dependents(obj)
        return obj

    def duplicate_object(self, obj: Dict, offset: int = 10, part_instance: Optional[PartInstance] = None) -> Dict:
        """
        Duplicate an object into the same component, with the next free id on its page, moved by `offset`.
        Templates of the original are kept, except for the moved position.
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :return: the rendered duplicate
        :raises ReadOnlyObjectError: for an included object (its templates need the variables of its instance)
        """
        self._check_editable(obj, part_instance)
        entry = self._entry(obj)
        source = copy.deepcopy(entry.source)
        source["id"] = next_free_id(self._working_objects, obj.get("page", 0))
        source["x"] = obj.get("x", 0) + offset
        source["y"] = obj.get("y", 0) + offset
        with self.edit(f"Duplicate {object_name(obj)}"):
            return self.add_object(str(entry.origin.file) if entry.is_included else entry.component, source, part_instance)

    def paste_objects(
        self,
        component: str,
        sources: List[Dict[str, Any]],
        page: int,
        screen: Tuple[int, int],
        position: Optional[Tuple[int, int]] = None,
        offset: int = 0,
        part_instance: Optional[PartInstance] = None,
    ) -> List[Dict]:
        """
        Add copies of objects (as written in a source file) to a page of a component, with the next free ids.
        They keep their layout: their top left corner goes to `position` (or stays where the originals were), moved by
        `offset` and kept on the screen. Objects inside of another (parentid) stay there if it is pasted too.
        Templates are kept, except for the moved positions. Nothing is added if one of them can't be rendered.
        In part mode, objects pasted into the part get a page and an id template like new objects of the part (see
        `add_object`), and are rendered with the variables of the instance that is shown.
        :param screen: the width and height of the screen
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :return: the rendered objects (in part mode those of the instance that is shown)
        :raises ReadOnlyObjectError: for a part outside of its part mode
        """
        if component in self._parts:
            return self._paste_into_part(component, sources, screen, position, offset, part_instance)
        taken = [obj for objects in self._working_objects.values() for obj in objects]
        new_ids: Dict[Any, int] = {}
        prepared = []
        for source in sources:
            source = copy.deepcopy(source)
            new_ids[source.get("id")] = next_free_id(OrderedDict(taken=taken), page)
            source["page"] = page
            source["id"] = new_ids[source.get("id")]
            taken.append(source)
            prepared.append(source)
        _link_parents(prepared, new_ids)
        rendered = [self._renderer.render_object(component, source) for source in prepared]
        self._place_pasted(prepared, rendered, screen, position, offset)
        with self.edit(f"Paste {len(prepared)} object{'' if len(prepared) == 1 else 's'}"):
            return [self.add_object(component, source) for source in prepared]

    def _paste_into_part(
        self,
        key: str,
        sources: List[Dict[str, Any]],
        screen: Tuple[int, int],
        position: Optional[Tuple[int, int]],
        offset: int,
        part_instance: Optional[PartInstance],
    ) -> List[Dict]:
        """Paste into a part in part mode: see `paste_objects`."""
        mode = self._check_part_mode(key, part_instance)
        instance = self._objects_of_instance(mode)
        if not instance:
            raise ValueError("The instance that is shown has no objects anymore: add an object first, or undo")
        # the pasted objects are rendered like the objects of the instance
        sample = self._entry(instance[0])
        part = self._parts[key]
        part_sources = [obj.source for obj in part.objects if not is_directive(obj.source)]
        new_ids: Dict[Any, Any] = {}
        prepared = []
        for source in sources:
            source = copy.deepcopy(source)
            page, object_id = new_part_object_ids(part_sources, {**source, "page": instance[0].get("page")})
            new_ids[source.get("id")] = object_id
            source["page"] = page
            source["id"] = object_id
            part_sources.append(source)
            prepared.append(source)
        _link_parents(prepared, new_ids)
        rendered = [self._renderer.render_object(sample.component, source, sample.scope) for source in prepared]
        self._place_pasted(prepared, rendered, screen, position, offset)
        with self.edit(f"Paste {len(prepared)} object{'' if len(prepared) == 1 else 's'} into the part"):
            return self._append_to_part(key, prepared, mode)

    @staticmethod
    def _place_pasted(
        prepared: List[Dict[str, Any]],
        rendered: List[Dict[str, Any]],
        screen: Tuple[int, int],
        position: Optional[Tuple[int, int]],
        offset: int,
    ):
        """Move the pasted objects (their top left corner) to the position, or by the offset, and keep them on the screen."""
        top_level = [(source, obj) for source, obj in zip(prepared, rendered) if "parentid" not in source]
        if top_level:
            left = min(obj.get("x", 0) for _, obj in top_level)
            top = min(obj.get("y", 0) for _, obj in top_level)
            width = max(obj.get("x", 0) + obj.get("w", 0) for _, obj in top_level) - left
            height = max(obj.get("y", 0) + obj.get("h", 0) for _, obj in top_level) - top
            x, y = position if position is not None else (left, top)
            x = max(0, min(x + offset, screen[0] - width))
            y = max(0, min(y + offset, screen[1] - height))
            for source, obj in top_level:
                source["x"] = obj.get("x", 0) + x - left
                source["y"] = obj.get("y", 0) + y - top

    def remove_object(self, obj: Dict, part_instance: Optional[PartInstance] = None):
        """
        :param part_instance: the instance of a part that is edited in part mode (see `read_only_reason`)
        :raises ReadOnlyObjectError: for an included object (outside of the instance of part mode)
        """
        self._check_editable(obj, part_instance)
        entry = self._entry(obj)
        if entry.is_included:
            part = self._parts[str(entry.origin.file)]
            with self.edit(f"Remove {object_name(obj)} from the part"):
                part.objects = [other for other in part.objects if other.uid != entry.instance[1]]
                self._reinclude_and_render({str(entry.origin.file)})
            return
        with self.edit(f"Remove {object_name(obj)}"):
            objects = self._working_objects[entry.component]
            objects.pop(next(i for i, other in enumerate(objects) if other is obj))
            del self._entries[id(obj)]
            self._render_dependents(obj)

    # --- undo ---

    @contextmanager
    def edit(self, description: str, merge_key: Optional[Hashable] = None) -> Iterator[None]:
        """
        Changes of the draft in this block are one step of the undo history (the changing methods of the session make a step
        each on their own). Edits inside of an edit are part of the outer one. The other devices that show a changed file
        render it again afterwards.
        :param description: what the edit does, e.g. "Move 3 objects"
        :param merge_key: steps with the same key, one right after the other, are merged into one (see `EditHistory.push`)
        """
        if self._edit is not None:
            yield
            return
        self._edit = (description, merge_key, self._config.state(), self._included_items())
        try:
            yield
        finally:
            description, merge_key, before, included_before = self._edit
            self._edit = None
            selected, self._selected_after_edit = self._selected_after_edit, None
            self._publish()
            after = self._config.state()
            if after != before:
                self._config.edited(description, before, after, merge_key)
                change = self._change_between(before, included_before, after, description)
                self._notify(replace(change, selected=selected))
                self._config.sync_others(self, before, after, description)

    def add_listener(self, listener: Callable[[DraftChange], None]):
        """
        Call the listener after every edit, undo and redo that changed the draft (not when it is loaded), also after an edit
        through another device of a file that this one shows.
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[DraftChange], None]):
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def undo_description(self) -> Optional[str]:
        """:return: what `undo` undoes, None if there is nothing to undo"""
        step = self.next_undo
        return None if step is None else step.description

    @property
    def redo_description(self) -> Optional[str]:
        """:return: what `redo` redoes, None if there is nothing to redo"""
        step = self.next_redo
        return None if step is None else step.description

    @property
    def next_undo(self) -> Optional[HistoryStep]:
        """What `undo` undoes (the newest step that changed a file the device shows), None if nothing; also if it is refused."""
        return self.step_to_undo()

    @property
    def next_redo(self) -> Optional[HistoryStep]:
        """What `redo` redoes, None if nothing; also if it is refused."""
        return self.step_to_redo()

    def step_to_undo(self, scope: Optional[FrozenSet[str]] = None) -> Optional[HistoryStep]:
        """:return: what `undo` with the scope undoes, None if nothing; also if it is refused"""
        return self._config.next_undo(self, scope)

    def step_to_redo(self, scope: Optional[FrozenSet[str]] = None) -> Optional[HistoryStep]:
        """:return: what `redo` with the scope redoes, None if nothing; also if it is refused"""
        return self._config.next_redo(self, scope)

    def display_paths(self, keys: Iterable[str]) -> List[str]:
        """:return: the paths of files and parts (by their keys, e.g. of a `HistoryStep`), relative to the config directory"""
        config_dir = config_root_of(self.device.path)
        return sorted(display_path(Path(key), config_dir) for key in keys)

    def end_merging(self):
        """The next edit is a step of its own, even with the merge key of the last one (e.g. another object was selected)."""
        self._config.history.seal()

    def object_uid(self, obj: Dict) -> int:
        """:return: what tells the object apart for the whole session, e.g. for a merge key of `edit`"""
        return self._entry(obj).uid

    def undo(self, scope: Optional[FrozenSet[str]] = None) -> Optional[DraftChange]:
        """
        Undo the newest edit of a file the device shows, also one made through another device (a shared file), like in
        IntelliJ: edits of files of other devices only are not undone. An edit of several files is undone in all of them.
        :param scope: the keys of the files and parts to undo in, some of those the device shows (a part tab: the part and the
            files that include its instance, see `PartFocus.undo_scope`); all of them by default
        :return: what was undone (the listeners get it too), None if there was nothing to undo
        :raise UndoRefusedError: if the edit changed several files and some of them changed since (in files outside of the
            scope): it can only be undone as a whole
        """
        try:
            return self._config.undo(self, scope)
        except BlockedStepError as ex:
            raise self._refused("undo", ex) from None

    def redo(self, scope: Optional[FrozenSet[str]] = None) -> Optional[DraftChange]:
        """:return: what was redone, None if there was nothing to redo (see `undo`)"""
        try:
            return self._config.redo(self, scope)
        except BlockedStepError as ex:
            raise self._refused("redo", ex) from None

    def _refused(self, verb: str, blocked: BlockedStepError) -> UndoRefusedError:
        changed = ", ".join(self.display_paths(blocked.files))
        return UndoRefusedError(
            f"Can't {verb} \"{blocked.step.description}\": it changed {', '.join(self.display_paths(blocked.step.files))} "
            f"as one step, and {changed} changed since. {verb.capitalize()} the newer changes of {changed} first, in the "
            "tab of a device that shows it."
        )

    # --- saving ---

    def changes(self) -> List[ComponentChanges]:
        """
        :return: what to change in the source files to save the draft, for every component and part the device shows that
            has changes (also changes made through another device)
        """
        return self._config.changes_of(self._keys, self._parts)

    def mark_saved(self, written: Dict[Path, str]):
        """
        The draft was saved: its files have this content now (see `changes`), with the objects of the draft in their order.
        The draft has no changes afterwards, and the undo history goes on: undoing a saved edit changes the draft again.
        Objects that were removed before saving come back as new objects (at the end of their file) when that is undone.
        The other devices that show a written file follow.
        :param written: the new content of every file that was written
        """
        self._config.mark_saved(self, written)

    def _saved(self, moved: Dict[str, Dict[int, int]], parts: Set[str], notify: bool):
        """
        Files of the `ConfigDraft` were saved (see `ConfigDraft.mark_saved`).
        :param moved: component key -> the old index of a kept source -> its new one, for the files that were written
        :param parts: the keys of the parts that were written
        :param notify: tell the listeners also if the device shows none of the files
        """
        written = [key for key in self._keys if key in moved]
        parts = {key for key in self._parts if key in parts}
        for key in written:
            indices = {obj.uid: obj.index for obj in self._file(key).objects}
            lines = _source_editor(self._file(key).component.content)
            for entry in map(self._entry, self._working_objects[key]):
                if entry.is_included:
                    # of a directive, which stays in the file
                    entry.index = moved[key][entry.index]
                    entry.origin = _moved_origin(entry.origin, entry.index, lines.line_of(entry.index))
                    entry.instance = _moved_instance(entry.instance, entry.index)
                else:
                    entry.index = indices[entry.uid]
        self._last_expansion = None
        for focus in self._part_focuses:
            mode = focus.instance
            if mode is not None and str(mode.steps[0][0]) in written:
                file, index, loop = mode.steps[0]
                focus.instance = replace(mode, steps=((file, moved[str(file)][index], loop),) + mode.steps[1:])
        if parts:
            # the lines of the included objects in their parts
            self._reinclude(set())
        if notify or written or parts:
            self._notify(DraftChange(ChangeKind.SAVE, "Save", objects=[], added=[], removed=False, pages=set()))

    # --- internals ---

    def _create(self, component: str, index: Optional[int], source: Dict[str, Any], uid: Optional[int] = None) -> Dict:
        return self._create_entry(DraftEntry(component=component, index=index, source=source, uid=0), uid)

    def _create_entry(self, entry: DraftEntry, uid: Optional[int] = None) -> Dict:
        entry.uid = self._config.new_uid() if uid is None else uid
        obj = self._rendered(entry)
        self._entries[id(obj)] = entry
        return obj

    def _rendered(self, entry: DraftEntry) -> Dict[str, Any]:
        return self._renderer.render_object(entry.component, entry.source, entry.scope)

    def _render(self, obj: Dict):
        self._apply(obj, self._rendered(self._entry(obj)))

    def _check_editable(self, obj: Dict, part_instance: Optional[PartInstance]):
        reason = self.read_only_reason(obj, part_instance)
        if reason is not None:
            raise ReadOnlyObjectError(f"{object_name(obj)} can't be changed here. {reason}")

    def _render_dependents(self, changed: Dict, name_before: Optional[str] = None):
        """
        Render the objects with templates again, after the source of `changed` changed (or it was added or removed):
        templates can refer to other objects (`{{ p1b2.x }}`). Only the objects that refer to `changed` are rendered, which
        matters: the variables of a component are expensive to compute.
        :param name_before: the name of `changed` (`p1b2`) before the change, if the change could rename it
        """
        self._set_draft_sources()
        if id(changed) in self._entries and self._refers_to_itself(changed):
            # it was rendered with the variables from before the change
            self._render(changed)
        self._render_referring({object_name(changed)} | ({name_before} if name_before else set()), skip=[changed])

    def _refers_to_itself(self, obj: Dict) -> bool:
        """:return: whether a template of the object uses the object (`this`, or its name)"""
        entry = self._entry(obj)
        values = [value for value in entry.source.values() if isinstance(value, str) and "{{" in value]
        return any(_THIS.search(value) for value in values) or bool(
            self._references_of(entry, obj.get("page")) & {object_name(obj), ANY_OBJECT}
        )

    def _set_draft_sources(self):
        self._renderer.set_draft_parts({Path(key): part.part_file() for key, part in self._parts.items()})
        self._renderer.set_draft_sources({key: self._file_sources(key) for key in self._working_objects})

    def _file_sources(self, key: str) -> List[Dict[str, Any]]:
        """:return: the objects of a component as the draft would write them: with its directives instead of what they include"""
        return [source for _index, source in self._indexed_file_sources(key)]

    def _indexed_file_sources(self, key: str) -> List[Tuple[Optional[int], Dict[str, Any]]]:
        """
        :return: (index in the source file, None for an added object; the source) of the objects of a component as the draft
            would write them (see `_file_sources`). The directives are in the order of the file, also those that include
            nothing, so none of them is further down than in the file: the expansion finds their lines in the file.
        """
        plain = [
            (entry.index, entry.source, None)
            for entry in map(self._entry, self._working_objects[key])
            if not entry.is_included
        ]
        return [(index, source) for index, source, _ in with_directives(self._file(key).directives, plain)]

    def _file(self, key: str) -> FileDraft:
        """:return: the draft of a file of the device in the `ConfigDraft`"""
        return self._config.files[key]

    def _publish(self):
        """Put the objects of the files of the device into the `ConfigDraft`, in their order (an edit changed them)."""
        for key in self._keys:
            self._file(key).objects = [
                PartObject(entry.uid, entry.index, entry.source)
                for entry in map(self._entry, self._working_objects[key])
                if not entry.is_included
            ]

    def _changed_directive(self, obj: Dict, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        """
        :return: the outermost `!include` of an included object with another `vars` or `for`, without the key if the
            mapping is empty
        """
        if key not in INCLUDE_KEYS:
            raise ValueError(f"An {INCLUDE} has only {VARS} and {FOR} to change, not {key}")
        directive = {**self.directive_of(obj), key: copy.deepcopy(value)}
        if not value:
            directive.pop(key)
        return directive

    def _expand_directive(
        self, component: str, index: int, directive: Dict[str, Any]
    ) -> Tuple[List[ExpandedObject], List[str]]:
        """
        Include a changed directive of a component of the draft: the file is expanded again, with the directive in its place.
        :param index: the index of the directive in the source file
        :return: the objects the directive includes (their outermost step is the directive in the file), and the errors it
            makes, which the file doesn't have with the directive as it is
        """
        key = (component, index, json.dumps(directive, sort_keys=True, default=str))
        if self._last_expansion is not None and self._last_expansion[0] == key:
            return self._last_expansion[1]
        indexed = self._indexed_file_sources(component)
        position = next(position for position, (other, _source) in enumerate(indexed) if other == index)
        sources = [source for _index, source in indexed]
        expansion = self._renderer.expand_objects(component, sources[:position] + [directive] + sources[position + 1 :])
        errors = [error.message for error in expansion.errors]
        if errors:
            # e.g. a missing part of another directive
            known = {error.message for error in self._renderer.expand_objects(component, sources).errors}
            errors = [error for error in errors if error not in known]
        # the expansion has the place of the directive in the objects of the draft, which can differ from the file
        line = _source_editor(self._file(component).component.content).line_of(index)
        objects = [
            replace(obj, origin=_moved_origin(obj.origin, index, line))
            for obj in expansion.objects
            if obj.origin.is_included and obj.origin.includes[0].index == position
        ]
        self._last_expansion = (key, (objects, errors))
        return objects, errors

    def _add_part_object(self, key: str, source: Dict[str, Any], part_instance: Optional[PartInstance]) -> Optional[Dict]:
        """Add an object to the end of a part, in part mode: see `add_object`."""
        mode = self._check_part_mode(key, part_instance)
        part = self._parts[key]
        page, object_id = new_part_object_ids([obj.source for obj in part.objects if not is_directive(obj.source)], source)
        source = {**copy.deepcopy(source), "page": page, "id": object_id}
        with self.edit(f"Add {source.get('obj', 'object')} to the part"):
            added = self._append_to_part(key, [source], mode)
        return added[0] if added else None

    @staticmethod
    def _check_part_mode(key: str, part_instance: Optional[PartInstance]) -> PartInstance:
        """:return: the instance of part mode :raises ReadOnlyObjectError: if it is not an instance of this part"""
        mode = part_instance
        if mode is None or str(mode.part) != key:
            raise ReadOnlyObjectError(f"Objects are added to {key} in part mode only")
        return mode

    def _append_to_part(self, key: str, sources: List[Dict[str, Any]], instance: PartInstance) -> List[Dict]:
        """
        Add objects to the end of a part (in a running edit), and select them in the instance that is shown.
        :return: their objects in that instance (none if the instance doesn't include them, e.g. a template of the page)
        """
        uids = [self._config.new_part_uid() for _ in sources]
        self._parts[key].objects.extend(PartObject(uid, None, source) for uid, source in zip(uids, sources))
        self._reinclude_and_render({key})
        by_uid = {self._entry(obj).instance[1]: obj for obj in self._objects_of_instance(instance)}
        added = [by_uid[uid] for uid in uids if uid in by_uid]
        self._selected_after_edit = added
        return added

    def _reinclude_and_render(self, changed_parts: Set[str]):
        """
        Include the directives of every file again, after a directive or a part changed, and render the objects that refer to
        the objects that changed.
        :param changed_parts: the keys of the parts whose objects changed
        """
        reincluded = self._reinclude(changed_parts)
        self._render_referring(reincluded.names, skip=reincluded.rendered)

    def _reinclude(self, changed_parts: Set[str], keys: Optional[Set[str]] = None) -> _Reincluded:
        """
        Expand the directives of every file of the draft again, with the directives and parts of the draft. Included objects
        that stay (see `DraftEntry.instance`) keep their rendered dict and are rendered again if their scope or their part
        changed; the others are added or removed, in the place of their directive.
        :param changed_parts: the keys of the parts whose objects changed
        :param keys: only the files with these component keys, by default all
        """
        self._set_draft_sources()
        result = _Reincluded(set(), [], [], [], set())
        for key in self._working_objects:
            if not self._file(key).directives or (keys is not None and key not in keys):
                continue
            indexed = self._indexed_file_sources(key)
            expansion = self._renderer.expand_objects(key, [source for _index, source in indexed])
            lines = _source_editor(self._file(key).component.content)
            staying = {self._entry(obj).instance: obj for obj in self._working_objects[key] if self._entry(obj).is_included}
            blocks: Dict[int, List[Dict]] = {}
            for expanded in expansion.objects:
                if not expanded.origin.is_included:
                    continue
                # the expansion has the place of the directive in the objects of the draft, which can differ from the file
                index = indexed[expanded.origin.includes[0].index][0]
                origin = _moved_origin(expanded.origin, index, lines.line_of(index))
                instance = _instance_key(origin, index, self._parts)
                source = _part_object(self._parts, origin.file, instance[1]).source
                obj = staying.pop(instance, None)
                if obj is None:
                    obj = self._create_entry(DraftEntry(key, index, source, 0, origin, expanded.scope, instance))
                    result.names.add(object_name(obj))
                    result.rendered.append(obj)
                    result.added.append(obj)
                    result.pages.add(obj.get("page"))
                else:
                    entry = self._entry(obj)
                    entry.index, entry.origin, entry.source = index, origin, source
                    if entry.scope != expanded.scope or str(origin.file) in changed_parts:
                        entry.scope = expanded.scope
                        result.names.add(object_name(obj))
                        result.pages.add(obj.get("page"))
                        self._render(obj)
                        result.names.add(object_name(obj))
                        result.pages.add(obj.get("page"))
                        result.rendered.append(obj)
                blocks.setdefault(index, []).append(obj)
            for removed in staying.values():
                result.names.add(object_name(removed))
                result.pages.add(removed.get("page"))
                result.removed.append(removed)
                del self._entries[id(removed)]
            plain = [
                obj for obj in self._working_objects[key] if id(obj) in self._entries and not self._entry(obj).is_included
            ]
            self._working_objects[key] = self._arranged(key, plain, blocks)
        return result

    def _arranged(self, key: str, plain: List[Dict], blocks: Dict[int, List[Dict]]) -> List[Dict]:
        """
        :param plain: the objects of a file that are not included, in their order
        :param blocks: the index of a directive in the file -> the objects it includes
        :return: the objects of the file: the plain objects, with the objects of each directive in its place (before the
            first object that is further down in the file, or before the objects added at the end)
        """
        directives = sorted(self._file(key).directives)
        indices = [self._entry(obj).index for obj in plain]
        last_in_file = max((position for position, index in enumerate(indices) if index is not None), default=-1)
        result = []
        for position, obj in enumerate(plain):
            index = indices[position]
            while directives and (position > last_in_file if index is None else directives[0] < index):
                result += blocks.get(directives.pop(0), [])
            result.append(obj)
        for index in directives:
            result += blocks.get(index, [])
        return result

    def _load_part(self, renderer: DraftRenderer, file: Path, fresh: bool, refresh: bool) -> PartDraft:
        """
        :return: the draft of a part: that of the `ConfigDraft` if it has changes (or `refresh` is off) or is the same on disk,
            else (or if `fresh`) as it is on disk
        """
        existing = self._config.parts.get(str(file))
        if existing is not None and not fresh and (not refresh or self._config.is_dirty(str(file))):
            return existing
        component = renderer.part_source(file)
        if existing is not None and not fresh and existing.component.content == component.content:
            return existing
        return self._config.part_from_disk(component)

    def _part_at(self, part: Path) -> PartDraft:
        """:return: a part of the draft, the path in any spelling :raises KeyError: if the draft has no such part"""
        resolved = Path(part).resolve()
        return next(draft for key, draft in self._parts.items() if _resolved(key) == resolved)

    def _instance_of_part(self, entry: DraftEntry, part: Path) -> Optional[PartInstance]:
        """
        :param part: resolved
        :return: the instance of the part an included object belongs to (it is in the part, or in a part it includes), None if
            it doesn't belong to one
        """
        if not entry.is_included:
            return None
        origin = entry.origin
        # the file each step includes
        files = [step.file for step in origin.includes[1:]] + [origin.file]
        for position, file in enumerate(files):
            if _resolved(str(file)) == part:
                return PartInstance(Path(file), entry.instance[0][: position + 1])
        return None

    @staticmethod
    def _in_part_mode(entry: DraftEntry, mode: PartInstance) -> bool:
        """:return: whether the object is an object of the part of part mode, in the instance that is edited"""
        return entry.is_included and Path(entry.origin.file) == mode.part and entry.instance[0] == mode.steps

    def _objects_of_instance(self, instance: PartInstance) -> List[Dict]:
        part = instance.part.resolve()
        return [obj for obj in self._all_objects() if self._instance_of_part(self._entry(obj), part) == instance]

    def _render_referring(self, names: Set[str], skip: List[Dict]):
        """Render the objects again whose templates refer to one of the named objects, except the ones to skip."""
        names_or_any = names | {ANY_OBJECT}
        for objects in self._working_objects.values():
            for obj in objects:
                entry = self._entry(obj)
                if not any(obj is other for other in skip) and self._references_of(entry, obj.get("page")) & names_or_any:
                    rendered = self._rendered(entry)
                    if rendered != obj:
                        self._apply(obj, rendered)

    def _references_of(self, entry: DraftEntry, page: Any) -> Set[str]:
        """
        :param page: the page of the object, for the objects of its page it names without a page (`b2`)
        :return: the objects the templates of an object refer to (`ANY_OBJECT` if that can't be told)
        """
        values = [value for value in entry.source.values() if isinstance(value, str)]
        if any(has_nested_templates(value) for value in values):
            # the names are built by templates, which need the variables of the component
            return self._renderer.referenced_objects(entry.component, entry.source, page, entry.scope)
        return set().union(*(referenced_objects(value, {}, page) for value in values))

    def _render_with(self, obj: Dict, key: str, value: Any) -> Dict:
        """:return: the object rendered with a different source value, without changing it"""
        entry = self._entry(obj)
        return self._renderer.render_object(entry.component, {**entry.source, key: value}, entry.scope)

    def _apply(self, obj: Dict, rendered: Dict):
        # the preview holds the rendered dict: keep its identity
        obj.clear()
        obj.update(rendered)

    def _state(self) -> DraftState:
        """The state of the `ConfigDraft`. The sources in it are shared with other states: never change them."""
        return self._config.state()

    def _included_items(self) -> Dict[int, Tuple[int, Any]]:
        """:return: uid -> (the uid of its part object, its scope) of the included objects, see `_change_between`"""
        return {
            entry.uid: (entry.instance[1], entry.scope) for entry in map(self._entry, self._all_objects()) if entry.is_included
        }

    def _compared_items(
        self, state: DraftState, included: Dict[int, Tuple[int, Any]]
    ) -> Dict[int, Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
        """:return: uid -> what tells whether an object of the device changed: its source, and the scope of an included object"""
        result: Dict[int, Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = {
            uid: (source, None) for key in self._keys for uid, _index, source in state.files[key].objects
        }
        part_sources = {uid: source for key in self._parts for uid, _index, source in state.parts[key].objects}
        result.update({uid: (part_sources[part_uid], scope) for uid, (part_uid, scope) in included.items()})
        return result

    def _sync(self, before: DraftState, after: DraftState, kind: ChangeKind, description: str) -> Optional[DraftChange]:
        """
        Follow a change of the `ConfigDraft` (an undo or redo, or an edit through another device): render the files and parts
        of the device that changed again, and tell the listeners. Objects that stay keep their rendered dict.
        :return: what changed for the device, None if it shows none of the changed files
        """
        changed_files, changed_parts = before.changed(after)
        keys = [key for key in self._keys if key in changed_files]
        parts = {key for key in self._parts if key in changed_parts}
        if not keys and not parts:
            return None
        self._last_expansion = None
        changed: List[Dict] = []
        added: List[Dict] = []
        removed: List[Dict] = []
        names: Set[str] = set()
        pages: Set[Any] = set()
        # every file with directives includes them again if a part changed
        reinclude: Optional[Set[str]] = None if parts else set()
        for key in keys:
            old_sources = {uid: source for uid, _index, source in before.files[key].objects}
            new_sources = {uid: source for uid, _index, source in after.files[key].objects}
            current: Dict[int, Dict] = {}
            blocks: Dict[int, List[Dict]] = {}
            for obj in self._working_objects[key]:
                entry = self._entry(obj)
                if entry.is_included:
                    blocks.setdefault(entry.index, []).append(obj)
                else:
                    current[entry.uid] = obj
            plain = []
            for part_object in self._file(key).objects:
                obj = current.pop(part_object.uid, None)
                if obj is None:
                    # rendered below, with the sources of the draft
                    obj = {}
                    self._entries[id(obj)] = DraftEntry(key, part_object.index, part_object.source, part_object.uid)
                    added.append(obj)
                else:
                    entry = self._entry(obj)
                    entry.source, entry.index = part_object.source, part_object.index
                    if old_sources.get(part_object.uid) != new_sources[part_object.uid]:
                        names.add(object_name(obj))
                        pages.add(obj.get("page"))
                        changed.append(obj)
                plain.append(obj)
            for obj in current.values():
                names.add(object_name(obj))
                pages.add(obj.get("page"))
                removed.append(obj)
                del self._entries[id(obj)]
            self._working_objects[key] = self._arranged(key, plain, blocks)
            if reinclude is not None and before.files[key].directives != after.files[key].directives:
                reinclude.add(key)

        # with the sources of the draft: templates can refer to other objects
        if reinclude is None or reinclude:
            reincluded = self._reinclude(parts, reinclude)
        else:
            self._set_draft_sources()
            reincluded = _Reincluded(set(), [], [], [], set())
        for obj in changed + added:
            self._render(obj)
        names |= {object_name(obj) for obj in changed + added} | reincluded.names
        pages |= {obj.get("page") for obj in changed + added} | reincluded.pages
        rendered = changed + added + reincluded.rendered
        self._render_referring(names, skip=rendered)
        rendered_ids = {id(obj) for obj in rendered}
        result = DraftChange(
            kind=kind,
            description=description,
            objects=[obj for obj in self._all_objects() if id(obj) in rendered_ids],
            added=added + reincluded.added,
            removed=bool(removed or reincluded.removed),
            pages=pages,
        )
        self._notify(result)
        return result

    def _change_between(
        self, before: DraftState, included_before: Dict[int, Tuple[int, Any]], after: DraftState, description: str
    ) -> DraftChange:
        """:return: what an edit of the device changed, from the state (and the included objects) before it to the state after it"""
        old = self._compared_items(before, included_before)
        new = self._compared_items(after, self._included_items())
        objects = [obj for obj in self._all_objects() if old.get(self._entry(obj).uid) != new[self._entry(obj).uid]]
        return DraftChange(
            kind=ChangeKind.EDIT,
            description=description,
            objects=objects,
            added=[obj for obj in objects if self._entry(obj).uid not in old],
            removed=any(uid not in new for uid in old),
            pages={obj.get("page") for obj in objects},
        )

    def _all_objects(self) -> Iterator[Dict]:
        return (obj for objects in self._working_objects.values() for obj in objects)

    def _notify(self, change: DraftChange):
        for listener in list(self._listeners):
            listener(change)

    def _entry(self, obj: Dict) -> DraftEntry:
        return self._entries[id(obj)]


@lru_cache(maxsize=256)
def _resolved(path: str) -> Path:
    return Path(path).resolve()


def _link_parents(prepared: List[Dict[str, Any]], new_ids: Dict[Any, Any]):
    """Pasted objects stay inside of a pasted object (`parentid`), the others are on the page."""
    for source in prepared:
        if "parentid" in source and source["parentid"] in new_ids:
            source["parentid"] = new_ids[source["parentid"]]
        else:
            source.pop("parentid", None)


def _part_object(parts: Dict[str, PartDraft], file: Path, uid: int) -> PartObject:
    return next(obj for obj in parts[str(file)].objects if obj.uid == uid)


def _instance_key(origin: ObjectOrigin, index: int, parts: Dict[str, PartDraft]) -> Tuple[Tuple[StepKey, ...], int]:
    """
    :param origin: an origin from an expansion with these parts (its indices in parts are those of their objects there)
    :param index: the index of the outermost directive in its file
    :param parts: the parts of the draft
    :return: what tells the included object apart (see `DraftEntry.instance`)
    """
    steps = tuple(
        (
            Path(step.file),
            index if position == 0 else parts[str(step.file)].objects[step.index].uid,
            json.dumps(step.loop, sort_keys=True, default=str),
        )
        for position, step in enumerate(origin.includes)
    )
    return steps, parts[str(origin.file)].objects[origin.index].uid


def _moved_instance(instance: Tuple[Tuple[StepKey, ...], int], index: int) -> Tuple[Tuple[StepKey, ...], int]:
    """:return: the instance key of an included object whose outermost directive is at another index of its file"""
    steps, uid = instance
    file, _index, loop = steps[0]
    return ((file, index, loop),) + steps[1:], uid


def _moved_origin(origin: ObjectOrigin, index: int, line: int) -> ObjectOrigin:
    """:return: the origin of an included object whose outermost directive is at another index and line of its file"""
    step: IncludeStep = replace(origin.includes[0], index=index, line=line)
    return replace(origin, includes=(step,) + origin.includes[1:])
