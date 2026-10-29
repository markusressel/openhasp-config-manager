import copy
import itertools
import json
import re
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple, Hashable, Iterator, Callable, NamedTuple

from jinja2 import TemplateError

from openhasp_config_manager.gui.domain.draft.model import (
    ChangeKind,
    ComponentChanges,
    ComponentSource,
    DraftChange,
    DraftEntry,
    DraftItem,
    DraftRenderer,
    DraftState,
    PartDraft,
    PartInstance,
    PartObject,
    StepKey,
)
from openhasp_config_manager.gui.domain.draft.edit_history import EditHistory
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

# stands for every object: the objects a template refers to can't be told
ANY_OBJECT = "*"
# the object itself in its templates
_THIS = re.compile(rf"\b{THIS}\b")


class _Rendered(NamedTuple):
    """A draft rendered from the files on disk (see `PlateSession._render_from_disk`)."""

    working_objects: OrderedDict[str, List[Dict]]
    # by id of the rendered object
    entries: Dict[int, DraftEntry]
    # component key -> the errors of its directives
    include_errors: Dict[str, List[IncludeError]]
    # component key -> index in the file -> the copy of a directive
    directives: Dict[str, Dict[int, Dict[str, Any]]]
    # part key -> the copy of the part
    parts: OrderedDict[str, PartDraft]


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
    The draft of a device's pages (of one cmd component) during an app session.

    The draft keeps every object twice: rendered (`working_objects`, shown in the preview) and as written in its source
    file, with templates. Edits change the source and render the object again, so the draft can be saved back into the
    source files without losing templates (see `changes()`).

    The directives of a file (`!include`) are replaced by the objects they include. Those are shown like the others, but are
    read-only: they are written in another file (the part), once for all of its instances. The `vars` and `for` of a directive
    can be changed (`set_directive_value`): its objects are included again. Saving writes the directives only where they
    changed.

    The draft keeps the parts too (`PartDraft`): the included objects of all instances of a part object share its source. In
    part mode (`enter_part_mode`) the objects of one instance of a part can be changed like the objects of a file; every
    instance follows, and saving writes the part.
    """

    def __init__(self, device: Device):
        self.device = device
        self._components: OrderedDict[str, ComponentSource] = OrderedDict()
        self._renderer: Optional[DraftRenderer] = None
        self._working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        # id(rendered object) -> its source
        self._entries: Dict[int, DraftEntry] = {}
        self._uids = itertools.count()
        self._loaded = False
        self._history: EditHistory[DraftState] = EditHistory()
        # uid -> the copy of its source in the last state taken: states share the sources that didn't change (memory)
        self._frozen_sources: Dict[int, Dict[str, Any]] = {}
        # the edit that is running (see `edit`): its description, merge key and the state before it
        self._edit: Optional[Tuple[str, Optional[Hashable], DraftState]] = None
        self._listeners: List[Callable[[DraftChange], None]] = []
        # component key -> the errors of its directives, when it was loaded
        self._include_errors: Dict[str, List[IncludeError]] = {}
        # component key -> index of a directive in the source file -> the directive as the draft has it
        self._directives: Dict[str, Dict[int, Dict[str, Any]]] = {}
        # (component key, index) -> the copy of a directive in the last state taken (see `_frozen_sources`)
        self._frozen_directives: Dict[Tuple[str, int], Dict[str, Any]] = {}
        # the objects to select after the running edit (see `DraftChange.selected`)
        self._selected_after_edit: Optional[List[Dict]] = None
        # the last expansion of a changed directive (see `_expand_directive`): its key, and the result
        self._last_expansion: Optional[Tuple[Tuple[str, int, str], Tuple[List[ExpandedObject], List[str]]]] = None
        # part key (its path as the origins of the included objects have it) -> the part as the draft has it
        self._parts: OrderedDict[str, PartDraft] = OrderedDict()
        self._part_uids = itertools.count()
        # part object uid -> the copy of its source in the last state taken (see `_frozen_sources`)
        self._frozen_part_sources: Dict[int, Dict[str, Any]] = {}
        # the instance of a part whose objects can be changed, None outside of part mode
        self._part_mode: Optional[PartInstance] = None

        self._dirty = False
        # when the draft was read from the files on disk the last time (loaded, reverted)
        self.loaded_at: Optional[datetime] = None

    def load(self, components: List[ComponentSource], renderer: DraftRenderer):
        """
        Initializes the draft from the components as they are on disk. If they can't be rendered, this raises and the
        draft stays as it was.
        """
        components = OrderedDict((component.key, component) for component in components)
        rendered = self._render_from_disk(components, renderer)
        self._components = components
        self._renderer = renderer
        self._replace_with(rendered)
        self._loaded = True

    def reset_to_disk(self):
        """
        Discards all changes of the draft and its undo history. The rendered objects are new objects afterwards. Part mode
        goes on in the instance that is included at the same place, if there is one. If the files can't be rendered, this
        raises and the draft stays as it was.
        """
        mode = self._part_mode
        # the uids of the parts are new afterwards
        described = None if mode is None or not self._objects_of_instance(mode) else self.describe_instance(mode)
        try:
            rendered = self._render_from_disk(self._components, self._renderer)
        except Exception:
            # the renderer sees the objects and parts of the draft again
            self._set_draft_sources()
            raise
        self._replace_with(rendered)
        if described is not None:
            self._part_mode = next(
                (instance for instance in self.part_instances(mode.part) if self.describe_instance(instance) == described),
                None,
            )

    def _render_from_disk(self, components: OrderedDict[str, ComponentSource], renderer: DraftRenderer) -> _Rendered:
        """:return: the draft as the files are on disk (nothing of the session is changed, except for the renderer)"""
        working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        entries: Dict[int, DraftEntry] = {}
        include_errors: Dict[str, List[IncludeError]] = {}
        directives = {
            component.key: {
                index: copy.deepcopy(source) for index, source in enumerate(component.sources) if is_directive(source)
            }
            for component in components.values()
        }
        parts: OrderedDict[str, PartDraft] = OrderedDict()
        renderer.set_draft_parts({})
        renderer.set_draft_sources({component.key: component.sources for component in components.values()})
        expansions = {key: renderer.expand_objects(key, component.sources) for key, component in components.items()}
        # the parts the files include, also those that only have directives
        for expansion in expansions.values():
            for expanded in expansion.objects:
                for file in [expanded.origin.file, *(step.file for step in expanded.origin.includes[1:])]:
                    if expanded.origin.is_included and str(file) not in parts:
                        parts[str(file)] = self._load_part(renderer, file)
        # from now on the expansions include the parts of the draft, whose objects the included objects share
        renderer.set_draft_parts({Path(key): part.part_file() for key, part in parts.items()})
        for key, component in components.items():
            expansion = renderer.expand_objects(key, component.sources)
            include_errors[key] = expansion.errors
            objects = []
            for expanded in expansion.objects:
                origin = expanded.origin
                if origin.is_included:
                    instance = _instance_key(origin, origin.includes[0].index, parts)
                    entry = DraftEntry(
                        key,
                        origin.includes[0].index,
                        _part_object(parts, origin.file, instance[1]).source,
                        0,
                        origin=origin,
                        scope=expanded.scope,
                        instance=instance,
                    )
                else:
                    entry = DraftEntry(key, origin.index, copy.deepcopy(expanded.source), 0)
                entry.uid = next(self._uids)
                obj = renderer.render_object(entry.component, entry.source, entry.scope)
                entries[id(obj)] = entry
                objects.append(obj)
            working_objects[key] = objects
        return _Rendered(working_objects, entries, include_errors, directives, parts)

    def _replace_with(self, rendered: _Rendered):
        self._working_objects, self._entries, self._include_errors, self._directives, self._parts = rendered
        self._history.clear()
        self._frozen_sources = {}
        self._frozen_directives = {}
        self._frozen_part_sources = {}
        self._last_expansion = None
        self._part_mode = None
        self._dirty = False
        self.loaded_at = datetime.now(timezone.utc)

    @property
    def is_part_alone(self) -> bool:
        """Whether the draft shows a part on its own (see `load_part_alone`), not the pages of a device."""
        return any(component.is_scratch for component in self._components.values())

    @property
    def is_dirty(self) -> bool:
        """Whether the draft differs from the files it was loaded from."""
        return self._dirty

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
        return list(self._components.values())

    # --- reading ---

    def source_of(self, obj: Dict) -> Dict[str, Any]:
        """:return: the object as written in its source file (do not change it)"""
        return self._entry(obj).source

    def component_of(self, obj: Dict) -> ComponentSource:
        return self._components[self._entry(obj).component]

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

    def read_only_reason(self, obj: Dict) -> Optional[str]:
        """
        :return: why the object can't be changed in the draft, None if it can. In part mode only the objects of the part in the
            instance that is edited can be changed.
        """
        entry = self._entry(obj)
        origin = entry.origin
        mode = self._part_mode
        if mode is None and origin is None:
            return None
        config_dir = config_root_of(self.device.path)
        if mode is not None:
            if self._in_part_mode(entry):
                return None
            part = display_path(mode.part, config_dir)
            if self.is_selectable(obj):
                inner = f"{display_path(origin.file, config_dir)}:{origin.line}"
                return f"It is included from {inner}, by an {INCLUDE} inside of the part {part}: edit that part."
            return f"In part mode only the objects of the part {part} (of the instance that is shown) can be changed."
        part = f"{display_path(origin.file, config_dir)}:{origin.line}"
        return (
            f"It is included from {part} ({describe_includes(origin.includes, config_dir)}). Change it in that file, or the "
            f"vars of the {INCLUDE}."
        )

    # --- part mode ---

    @property
    def part_mode(self) -> Optional[PartInstance]:
        """The instance of a part whose objects can be changed (see `enter_part_mode`), None outside of part mode."""
        return self._part_mode

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

    def enter_part_mode(self, instance: PartInstance):
        """
        Edit the objects of a part in one of its instances: they can be changed like the objects of a file (the other objects
        can't), and every instance of the part follows. The draft keeps its changes when part mode ends.
        :raises ValueError: if the instance is not in the draft, or the part is also a file of the draft
        """
        if instance not in self.part_instances(instance.part):
            raise ValueError(f"{instance.part} has no such instance in the draft")
        if self.component_at(instance.part) is not None:
            raise ValueError(
                f"{instance.part.name} is also a page file of the device: change its objects there, not as a part"
            )
        self._part_mode = instance

    def leave_part_mode(self):
        self._part_mode = None

    def part_source(self, part: Path) -> ComponentSource:
        """:return: a part of the draft (the path in any spelling) as it was read from disk"""
        return self._part_at(part).component

    def is_selectable(self, obj: Dict) -> bool:
        """:return: whether the object can be selected: in part mode only the objects of the instance that is edited"""
        mode = self._part_mode
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
        return self._directives[entry.component][entry.index]

    def include_errors(self) -> Dict[str, List[IncludeError]]:
        """:return: component key -> what is wrong with the directives of its file (as loaded from disk)"""
        return self._include_errors

    def component_at(self, path: Path) -> Optional[ComponentSource]:
        """:return: the component of a file (the path in any spelling), None if the draft has no objects of that file"""
        resolved = path.resolve()
        return next((component for component in self._components.values() if component.path.resolve() == resolved), None)

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

    def check_value(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        """
        Check a value for a property, as written in the source (a literal or a template), before setting it.
        :return: why it can't be set, or None if it can
        """
        reason = self.read_only_reason(obj)
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

    def set_source_value(self, obj: Dict, key: str, value: Any):
        """
        Set a property as it is written in the source, a literal or a template, and render the object again.
        Nothing changes if the object can't be rendered with it (see check_value).
        :raises ReadOnlyObjectError: for an included object
        """
        self._check_editable(obj)
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
        values or templates), and include its part again: objects of its instances that stay keep their rendered dict (and
        are rendered again), the others are added or removed. The object stays selected if it is still included.
        :raises InvalidDirectiveError: if the directive would have an error (see `check_directive_value`); nothing changes then
        """
        error = self.check_directive_value(obj, key, value)
        if error is not None:
            raise InvalidDirectiveError(error)
        entry = self._entry(obj)
        with self.edit(f"Change {key} of the {INCLUDE} at line {self.line_of(obj)}"):
            self._directives[entry.component][entry.index] = self._changed_directive(obj, key, value)
            self._reinclude_and_render(set())
            self._selected_after_edit = [obj] if id(obj) in self._entries else []

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

    def use_pixel_position(self, obj: Dict):
        """Replace a template or a percentage in x and y with the pixels it renders to, so the object can be moved."""
        self._check_editable(obj)
        with self.edit(f"Use pixels for x/y of {object_name(obj)}"):
            for key in ("x", "y"):
                if self.is_template(obj, key) or self.is_percentage(obj, key):
                    self.set_source_value(obj, key, obj.get(key, 0))

    def remove_source_value(self, obj: Dict, key: str):
        """
        Remove a property the draft added to the source (e.g. resetting a theme default that was changed),
        and render the object again.
        """
        self._check_editable(obj)
        before = object_name(obj)
        with self.edit(f"Reset {key} of {before}"):
            entry = self._entry(obj)
            entry.source.pop(key)
            if entry.is_included:
                self._reinclude_and_render({str(entry.origin.file)})
                return
            self._render(obj)
            self._render_dependents(obj, before)

    def add_object(self, component: str, source: Dict[str, Any]) -> Optional[Dict]:
        """
        Add an object to the end of a component (it is drawn on top, and saved to the end of the file).
        :param component: a component key, or in part mode the key of the part (`PartInstance.part`): the object is added to
            every instance then, with templates for its page and id (see `new_part_object_ids`)
        :return: the rendered object (in part mode: in the instance that is edited, None if it can't be included there)
        """
        if component in self._parts:
            return self._add_part_object(component, source)
        with self.edit(f"Add {source.get('obj', 'object')}"):
            obj = self._create(component, None, copy.deepcopy(source))
            self._working_objects[component].append(obj)
            self._render_dependents(obj)
        return obj

    def duplicate_object(self, obj: Dict, offset: int = 10) -> Dict:
        """
        Duplicate an object into the same component, with the next free id on its page, moved by `offset`.
        Templates of the original are kept, except for the moved position.
        :return: the rendered duplicate
        :raises ReadOnlyObjectError: for an included object (its templates need the variables of its instance)
        """
        self._check_editable(obj)
        entry = self._entry(obj)
        source = copy.deepcopy(entry.source)
        source["id"] = next_free_id(self._working_objects, obj.get("page", 0))
        source["x"] = obj.get("x", 0) + offset
        source["y"] = obj.get("y", 0) + offset
        with self.edit(f"Duplicate {object_name(obj)}"):
            return self.add_object(str(entry.origin.file) if entry.is_included else entry.component, source)

    def paste_objects(
        self,
        component: str,
        sources: List[Dict[str, Any]],
        page: int,
        screen: Tuple[int, int],
        position: Optional[Tuple[int, int]] = None,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Add copies of objects (as written in a source file) to a page of a component, with the next free ids.
        They keep their layout: their top left corner goes to `position` (or stays where the originals were), moved by
        `offset` and kept on the screen. Objects inside of another (parentid) stay there if it is pasted too.
        Templates are kept, except for the moved positions. Nothing is added if one of them can't be rendered.
        In part mode, objects pasted into the part get a page and an id template like new objects of the part (see
        `add_object`), and are rendered with the variables of the instance that is shown.
        :param screen: the width and height of the screen
        :return: the rendered objects (in part mode those of the instance that is shown)
        :raises ReadOnlyObjectError: for a part outside of part mode
        """
        if component in self._parts:
            return self._paste_into_part(component, sources, screen, position, offset)
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
    ) -> List[Dict]:
        """Paste into a part in part mode: see `paste_objects`."""
        mode = self._check_part_mode(key)
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
            return self._append_to_part(key, prepared)

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

    def remove_object(self, obj: Dict):
        """:raises ReadOnlyObjectError: for an included object"""
        self._check_editable(obj)
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
        each on their own). Edits inside of an edit are part of the outer one.
        :param description: what the edit does, e.g. "Move 3 objects"
        :param merge_key: steps with the same key, one right after the other, are merged into one (see `EditHistory.push`)
        """
        if self._edit is not None:
            yield
            return
        self._edit = (description, merge_key, self._state())
        try:
            yield
        finally:
            description, merge_key, before = self._edit
            self._edit = None
            selected, self._selected_after_edit = self._selected_after_edit, None
            after = self._state()
            self._dirty = self._differs_from_files()
            if after != before:
                self._history.push(description, before, after, merge_key)
                self._notify(replace(self._change_between(before, after, description), selected=selected))

    def add_listener(self, listener: Callable[[DraftChange], None]):
        """Call the listener after every edit, undo and redo that changed the draft (not when it is loaded)."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[DraftChange], None]):
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def undo_description(self) -> Optional[str]:
        """:return: what `undo` undoes, None if there is nothing to undo"""
        return self._history.undo_description

    @property
    def redo_description(self) -> Optional[str]:
        """:return: what `redo` redoes, None if there is nothing to redo"""
        return self._history.redo_description

    def end_merging(self):
        """The next edit is a step of its own, even with the merge key of the last one (e.g. another object was selected)."""
        self._history.seal()

    def object_uid(self, obj: Dict) -> int:
        """:return: what tells the object apart for the whole session, e.g. for a merge key of `edit`"""
        return self._entry(obj).uid

    def undo(self) -> Optional[DraftChange]:
        """:return: what was undone (the listeners get it too), None if there was nothing to undo"""
        step = self._history.undo()
        return None if step is None else self._restore(step.before, step.description, ChangeKind.UNDO)

    def redo(self) -> Optional[DraftChange]:
        """:return: what was redone (the listeners get it too), None if there was nothing to redo"""
        step = self._history.redo()
        return None if step is None else self._restore(step.after, step.description, ChangeKind.REDO)

    # --- saving ---

    def changes(self) -> List[ComponentChanges]:
        """
        :return: what to change in the source files to save the draft, for every component and part that has changes
        """
        result = [
            self._component_changes(
                component,
                self._directives[component.key],
                [
                    (entry.index, entry.source)
                    for entry in map(self._entry, self._working_objects[component.key])
                    if not entry.is_included
                ],
            )
            for component in self._components.values()
            # what shows a part on its own is in no file
            if not component.is_scratch
        ]
        result += [
            self._component_changes(part.component, {}, [(obj.index, obj.source) for obj in part.objects])
            for part in self._parts.values()
        ]
        return [changes for changes in result if changes.changes or changes.deletions or changes.additions]

    @staticmethod
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
                raise AssertionError(f"Removing keys from a directive is not supported: {removed}")
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

    def mark_saved(self, written: Dict[Path, str]):
        """
        The draft was saved: its files have this content now (see `changes`), with the objects of the draft in their order.
        The draft has no changes afterwards, and the undo history goes on: undoing a saved edit changes the draft again.
        Objects that were removed before saving come back as new objects (at the end of their file) when that is undone.
        :param written: the new content of every file that was written
        """
        new_indices: Dict[int, int] = {}
        rewritten = set()
        # component key -> the old index of a kept source -> its new one
        moved: Dict[str, Dict[int, int]] = {}
        lines: Dict[str, JsonlSourceEditor] = {}
        for key, component in list(self._components.items()):
            if component.path not in written:
                continue
            rewritten.add(key)
            entries = [self._entry(obj) for obj in self._working_objects[key]]
            # the file keeps its directives and the objects that were not removed in their order, the new ones are at its end
            kept = dict(self._directives[key])
            kept |= {entry.index: entry.source for entry in entries if entry.index is not None and not entry.is_included}
            moved[key] = {old: new for new, old in enumerate(sorted(kept))}
            added = [entry for entry in entries if entry.index is None]
            new_index = {entry.uid: len(kept) + position for position, entry in enumerate(added)}
            for entry in entries:
                entry.index = moved[key][entry.index] if entry.index is not None else new_index[entry.uid]
                new_indices[entry.uid] = entry.index
            sources = [kept[old] for old in sorted(kept)] + [entry.source for entry in added]
            self._components[key] = replace(
                component, content=written[component.path], sources=[copy.deepcopy(source) for source in sources]
            )
            self._directives[key] = {moved[key][index]: directive for index, directive in self._directives[key].items()}
            lines[key] = _source_editor(written[component.path])
            for entry in entries:
                if entry.is_included:
                    entry.origin = _moved_origin(entry.origin, entry.index, lines[key].line_of(entry.index))
                    entry.instance = _moved_instance(entry.instance, entry.index)
        self._frozen_directives = {}

        # part key -> uid of a part object -> its new index
        part_indices: Dict[str, Dict[int, int]] = {}
        # part key -> uid of a part object -> its new line
        part_lines: Dict[str, Dict[int, int]] = {}
        for key, part in self._parts.items():
            if part.component.path not in written:
                continue
            # like a file: the objects that were not removed in their order, then the new ones
            kept = sorted(obj.index for obj in part.objects if obj.index is not None)
            moved_part = {old: new for new, old in enumerate(kept)}
            added = [obj for obj in part.objects if obj.index is None]
            part_indices[key] = {}
            for obj in part.objects:
                obj.index = moved_part[obj.index] if obj.index is not None else len(kept) + added.index(obj)
                part_indices[key][obj.uid] = obj.index
            sources = sorted(part.objects, key=lambda obj: obj.index)
            part.component = replace(
                part.component,
                content=written[part.component.path],
                sources=[copy.deepcopy(obj.source) for obj in sources],
            )
            editor = _source_editor(written[part.component.path])
            part_lines[key] = {obj.uid: editor.line_of(obj.index) for obj in part.objects}

        def translate(state: DraftState) -> DraftState:
            def item(key: str, values: DraftItem) -> DraftItem:
                if values.origin is None:
                    return values._replace(index=new_indices.get(values.uid)) if key in rewritten else values
                if key in rewritten:
                    # included: of a directive, which stays in the file
                    new = moved[key][values.index]
                    values = values._replace(
                        index=new,
                        origin=_moved_origin(values.origin, new, lines[key].line_of(new)),
                        instance=_moved_instance(values.instance, new),
                    )
                return values._replace(origin=_relined_origin(values.origin, values.instance, part_lines))

            return DraftState(
                objects={key: tuple(item(key, values) for values in objects) for key, objects in state.objects.items()},
                directives={
                    key: {moved[key][index]: directive for index, directive in directives.items()}
                    if key in rewritten
                    else directives
                    for key, directives in state.directives.items()
                },
                parts={
                    key: tuple((uid, part_indices[key].get(uid), source) for uid, _index, source in objects)
                    if key in part_indices
                    else objects
                    for key, objects in state.parts.items()
                },
            )

        self._history = self._history.mapped(translate)
        mode = self._part_mode
        if mode is not None and str(mode.steps[0][0]) in moved:
            file, index, loop = mode.steps[0]
            self._part_mode = replace(mode, steps=((file, moved[str(file)][index], loop),) + mode.steps[1:])
        if part_indices:
            # the lines of the included objects in their parts
            self._reinclude(set())
        self._dirty = self._differs_from_files()
        self._notify(DraftChange(ChangeKind.SAVE, "Save", objects=[], added=[], removed=False, pages=set()))

    # --- internals ---

    def _create(self, component: str, index: Optional[int], source: Dict[str, Any], uid: Optional[int] = None) -> Dict:
        return self._create_entry(DraftEntry(component=component, index=index, source=source, uid=0), uid)

    def _create_entry(self, entry: DraftEntry, uid: Optional[int] = None) -> Dict:
        entry.uid = next(self._uids) if uid is None else uid
        obj = self._rendered(entry)
        self._entries[id(obj)] = entry
        return obj

    def _rendered(self, entry: DraftEntry) -> Dict[str, Any]:
        return self._renderer.render_object(entry.component, entry.source, entry.scope)

    def _render(self, obj: Dict):
        self._apply(obj, self._rendered(self._entry(obj)))

    def _check_editable(self, obj: Dict):
        reason = self.read_only_reason(obj)
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
        directives = sorted(self._directives[key].items())
        result = []
        for entry in map(self._entry, self._working_objects[key]):
            if entry.is_included:
                continue
            while directives and (entry.index is None or directives[0][0] < entry.index):
                result.append(directives.pop(0))
            result.append((entry.index, entry.source))
        return result + directives

    def _changed_directive(self, obj: Dict, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        """:return: the outermost `!include` of an included object with another `vars` or `for`"""
        if key not in INCLUDE_KEYS:
            raise ValueError(f"An {INCLUDE} has only {VARS} and {FOR} to change, not {key}")
        return {**self.directive_of(obj), key: copy.deepcopy(value)}

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
        line = _source_editor(self._components[component].content).line_of(index)
        objects = [
            replace(obj, origin=_moved_origin(obj.origin, index, line))
            for obj in expansion.objects
            if obj.origin.is_included and obj.origin.includes[0].index == position
        ]
        self._last_expansion = (key, (objects, errors))
        return objects, errors

    def _add_part_object(self, key: str, source: Dict[str, Any]) -> Optional[Dict]:
        """Add an object to the end of a part, in part mode: see `add_object`."""
        self._check_part_mode(key)
        part = self._parts[key]
        page, object_id = new_part_object_ids([obj.source for obj in part.objects if not is_directive(obj.source)], source)
        source = {**copy.deepcopy(source), "page": page, "id": object_id}
        with self.edit(f"Add {source.get('obj', 'object')} to the part"):
            added = self._append_to_part(key, [source])
        return added[0] if added else None

    def _check_part_mode(self, key: str) -> PartInstance:
        """:return: the instance of part mode :raises ReadOnlyObjectError: if the draft is not in part mode of this part"""
        mode = self._part_mode
        if mode is None or str(mode.part) != key:
            raise ReadOnlyObjectError(f"Objects are added to {key} in part mode only")
        return mode

    def _append_to_part(self, key: str, sources: List[Dict[str, Any]]) -> List[Dict]:
        """
        Add objects to the end of a part (in a running edit), and select them in the instance that is shown.
        :return: their objects in that instance (none if the instance doesn't include them, e.g. a template of the page)
        """
        uids = [next(self._part_uids) for _ in sources]
        self._parts[key].objects.extend(PartObject(uid, None, source) for uid, source in zip(uids, sources))
        self._reinclude_and_render({key})
        by_uid = {self._entry(obj).instance[1]: obj for obj in self._objects_of_instance(self._part_mode)}
        added = [by_uid[uid] for uid in uids if uid in by_uid]
        self._selected_after_edit = added
        return added

    def _reinclude_and_render(self, changed_parts: Set[str]):
        """
        Include the directives of every file again, after a directive or a part changed, and render the objects that refer to
        the objects that changed.
        :param changed_parts: the keys of the parts whose objects changed
        """
        names, rendered = self._reinclude(changed_parts)
        self._render_referring(names, skip=rendered)

    def _reinclude(self, changed_parts: Set[str]) -> Tuple[Set[str], List[Dict]]:
        """
        Expand the directives of every file of the draft again, with the directives and parts of the draft. Included objects
        that stay (see `DraftEntry.instance`) keep their rendered dict and are rendered again if their scope or their part
        changed; the others are added or removed, in the place of their directive.
        :param changed_parts: the keys of the parts whose objects changed
        :return: the names (before and after) of the objects that were added, removed or rendered again, and those rendered
        """
        self._set_draft_sources()
        names: Set[str] = set()
        rendered: List[Dict] = []
        for key in self._working_objects:
            if not self._directives[key]:
                continue
            indexed = self._indexed_file_sources(key)
            expansion = self._renderer.expand_objects(key, [source for _index, source in indexed])
            lines = _source_editor(self._components[key].content)
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
                    names.add(object_name(obj))
                    rendered.append(obj)
                else:
                    entry = self._entry(obj)
                    entry.index, entry.origin, entry.source = index, origin, source
                    if entry.scope != expanded.scope or str(origin.file) in changed_parts:
                        entry.scope = expanded.scope
                        names.add(object_name(obj))
                        self._render(obj)
                        names.add(object_name(obj))
                        rendered.append(obj)
                blocks.setdefault(index, []).append(obj)
            for removed in staying.values():
                names.add(object_name(removed))
                del self._entries[id(removed)]
            # the plain objects in their order, with the objects of each directive in its place
            directives = sorted(self._directives[key])
            result = []
            for obj in self._working_objects[key]:
                entry = self._entry(obj) if id(obj) in self._entries else None
                if entry is None or entry.is_included:
                    continue
                while directives and (entry.index is None or directives[0] < entry.index):
                    result += blocks.get(directives.pop(0), [])
                result.append(obj)
            for index in directives:
                result += blocks.get(index, [])
            self._working_objects[key] = result
        return names, rendered

    def _load_part(self, renderer: DraftRenderer, file: Path) -> PartDraft:
        component = renderer.part_source(file)
        objects = [
            PartObject(next(self._part_uids), index, copy.deepcopy(source)) for index, source in enumerate(component.sources)
        ]
        return PartDraft(component, objects)

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

    def _in_part_mode(self, entry: DraftEntry) -> bool:
        """:return: whether the object is an object of the part of part mode, in the instance that is edited"""
        mode = self._part_mode
        return (
            mode is not None and entry.is_included and Path(entry.origin.file) == mode.part and entry.instance[0] == mode.steps
        )

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
        """The sources in it are shared with other states: never change them."""
        return DraftState(
            objects={
                key: tuple(
                    DraftItem(
                        entry.uid,
                        entry.index,
                        # the source of an included object is that of its part object
                        None if entry.is_included else self._frozen_source(entry.uid, entry.source, self._frozen_sources),
                        entry.origin,
                        entry.scope,
                        entry.instance,
                    )
                    for entry in map(self._entry, objects)
                )
                for key, objects in self._working_objects.items()
            },
            directives={
                key: {index: self._frozen_directive(key, index) for index in directives}
                for key, directives in self._directives.items()
            },
            parts={
                key: tuple(
                    (obj.uid, obj.index, self._frozen_source(obj.uid, obj.source, self._frozen_part_sources))
                    for obj in part.objects
                )
                for key, part in self._parts.items()
            },
        )

    def _frozen_directive(self, key: str, index: int) -> Dict[str, Any]:
        """:return: a copy of a directive of the draft, the one of the last state if it didn't change since"""
        directive = self._directives[key][index]
        frozen = self._frozen_directives.get((key, index))
        if frozen is None or frozen != directive:
            frozen = copy.deepcopy(directive)
            self._frozen_directives[(key, index)] = frozen
        return frozen

    @staticmethod
    def _frozen_source(uid: int, source: Dict[str, Any], frozen_sources: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        """:return: a copy of the source of an object, the one of the last state if the source didn't change since"""
        frozen = frozen_sources.get(uid)
        if frozen is None or frozen != source:
            frozen = copy.deepcopy(source)
            frozen_sources[uid] = frozen
        return frozen

    def _differs_from_files(self) -> bool:
        for component in self._components.values():
            if component.is_scratch:
                # its vars are not saved
                continue
            if any(directive != component.sources[index] for index, directive in self._directives[component.key].items()):
                return True
            # the included objects follow their directives, which stay
            entries = [entry for entry in map(self._entry, self._working_objects[component.key]) if not entry.is_included]
            indices = [index for index, source in enumerate(component.sources) if not is_directive(source)]
            if len(entries) != len(indices) or any(
                entry.index != index or entry.source != component.sources[index] for index, entry in zip(indices, entries)
            ):
                return True
        for part in self._parts.values():
            if [obj.index for obj in part.objects] != list(range(len(part.component.sources))) or any(
                obj.source != source for obj, source in zip(part.objects, part.component.sources)
            ):
                return True
        return False

    def _restore(self, state: DraftState, description: str, kind: ChangeKind) -> DraftChange:
        """Change the draft to a state of the undo history. Objects that stay keep their rendered dict."""
        current = {self._entry(obj).uid: obj for objects in self._working_objects.values() for obj in objects}
        changed: List[Dict] = []
        added: List[Dict] = []
        names: Set[str] = set()
        pages: Set[Any] = set()
        self._directives = {
            key: {index: copy.deepcopy(directive) for index, directive in directives.items()}
            for key, directives in state.directives.items()
        }
        # the part objects whose source changed: their included objects are rendered again
        changed_part_objects = set()
        for key, items in state.parts.items():
            part = self._parts[key]
            existing = {obj.uid: obj for obj in part.objects}
            objects = []
            for uid, index, source in items:
                obj = existing.get(uid)
                if obj is None:
                    obj = PartObject(uid, index, copy.deepcopy(source))
                    changed_part_objects.add(uid)
                elif obj.source != source:
                    # the included objects share it
                    obj.source.clear()
                    obj.source.update(copy.deepcopy(source))
                    changed_part_objects.add(uid)
                obj.index = index
                objects.append(obj)
            part.objects = objects
        for key, items in state.objects.items():
            objects = []
            for item in items:
                source = (
                    copy.deepcopy(item.source)
                    if item.origin is None
                    else _part_object(self._parts, item.origin.file, item.instance[1]).source
                )
                obj = current.pop(item.uid, None)
                if obj is None:
                    entry = DraftEntry(key, item.index, source, 0, item.origin, item.scope, item.instance)
                    obj = self._create_entry(entry, uid=item.uid)
                    added.append(obj)
                    objects.append(obj)
                    continue
                entry = self._entry(obj)
                part_changed = item.instance is not None and item.instance[1] in changed_part_objects
                if (
                    (item.origin is None and entry.source != item.source)
                    or part_changed
                    or entry.origin != item.origin
                    or entry.scope is not item.scope
                ):
                    names.add(object_name(obj))
                    pages.add(obj.get("page"))
                    entry.source = source
                    entry.index, entry.origin, entry.scope, entry.instance = item.index, item.origin, item.scope, item.instance
                    changed.append(obj)
                else:
                    entry.index = item.index
                objects.append(obj)
            self._working_objects[key] = objects
        for removed in current.values():
            names.add(object_name(removed))
            pages.add(removed.get("page"))
            del self._entries[id(removed)]

        # with the restored sources: templates can refer to other objects
        self._set_draft_sources()
        for obj in changed + added:
            self._render(obj)
        names |= {object_name(obj) for obj in changed + added}
        pages |= {obj.get("page") for obj in changed + added}
        self._render_referring(names, skip=changed + added)
        self._dirty = self._differs_from_files()
        restored = DraftChange(
            kind=kind,
            description=description,
            objects=[obj for obj in self._all_objects() if any(obj is other for other in changed + added)],
            added=added,
            removed=bool(current),
            pages=pages,
        )
        self._notify(restored)
        return restored

    def _change_between(self, before: DraftState, after: DraftState, description: str) -> DraftChange:
        old = _compared_items(before)
        new = _compared_items(after)
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


def _compared_items(state: DraftState) -> Dict[int, Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    """:return: uid -> what tells whether an object of the state changed: its source, and the scope of an included object"""
    part_sources = {uid: source for objects in state.parts.values() for uid, _index, source in objects}
    return {
        item.uid: (item.source if item.instance is None else part_sources[item.instance[1]], item.scope)
        for objects in state.objects.values()
        for item in objects
    }


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


def _relined_origin(
    origin: ObjectOrigin, instance: Tuple[Tuple[StepKey, ...], int], part_lines: Dict[str, Dict[int, int]]
) -> ObjectOrigin:
    """
    :param part_lines: part key -> uid of a part object -> its line, for the parts that were saved
    :return: the origin of an included object with the lines its part objects and inner directives have in the saved parts
    (None for those that are not in their file anymore)
    """
    steps, uid = instance
    includes = tuple(
        replace(step, line=part_lines[str(step.file)].get(steps[position][1]))
        if position > 0 and str(step.file) in part_lines
        else step
        for position, step in enumerate(origin.includes)
    )
    line = part_lines[str(origin.file)].get(uid) if str(origin.file) in part_lines else origin.line
    return replace(origin, line=line, includes=includes)
