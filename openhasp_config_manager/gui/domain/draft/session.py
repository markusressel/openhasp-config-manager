import copy
import itertools
import json
import re
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple, Hashable, Iterator, Callable

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
)
from openhasp_config_manager.gui.domain.draft.edit_history import EditHistory
from openhasp_config_manager.gui.domain.draft.page_objects import next_free_id
from openhasp_config_manager.gui.domain.file_tree import config_root_of
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl.includes import (
    FOR,
    INCLUDE,
    INCLUDE_KEYS,
    VARS,
    ExpandedObject,
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
# the rendered objects per component, their entries (by id of the object), the errors of their directives, and the copies
# of the directives (component key -> index in the file -> directive)
type _Rendered = Tuple[
    OrderedDict[str, List[Dict]], Dict[int, DraftEntry], Dict[str, List[IncludeError]], Dict[str, Dict[int, Dict[str, Any]]]
]


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

        self._dirty = False

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
        Discards all changes of the draft and its undo history. The rendered objects are new objects afterwards. If the
        files can't be rendered, this raises and the draft stays as it was.
        """
        try:
            rendered = self._render_from_disk(self._components, self._renderer)
        except Exception:
            # the renderer sees the objects of the draft again
            self._set_draft_sources()
            raise
        self._replace_with(rendered)

    def _render_from_disk(self, components: OrderedDict[str, ComponentSource], renderer: DraftRenderer) -> _Rendered:
        """:return: the rendered objects per component, their entries, the errors and the copies of their directives"""
        working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        entries: Dict[int, DraftEntry] = {}
        include_errors: Dict[str, List[IncludeError]] = {}
        directives = {
            component.key: {
                index: copy.deepcopy(source) for index, source in enumerate(component.sources) if is_directive(source)
            }
            for component in components.values()
        }
        renderer.set_draft_sources({component.key: component.sources for component in components.values()})
        for component in components.values():
            expansion = renderer.expand_objects(component.key, component.sources)
            include_errors[component.key] = expansion.errors
            objects = []
            for expanded in expansion.objects:
                origin = expanded.origin
                if origin.is_included:
                    # the part's object is shared by its instances, and never changed
                    entry = DraftEntry(
                        component.key, origin.includes[0].index, expanded.source, 0, origin=origin, scope=expanded.scope
                    )
                else:
                    entry = DraftEntry(component.key, origin.index, copy.deepcopy(expanded.source), 0)
                entry.uid = next(self._uids)
                obj = renderer.render_object(entry.component, entry.source, entry.scope)
                entries[id(obj)] = entry
                objects.append(obj)
            working_objects[component.key] = objects
        return working_objects, entries, include_errors, directives

    def _replace_with(self, rendered: _Rendered):
        self._working_objects, self._entries, self._include_errors, self._directives = rendered
        self._history.clear()
        self._frozen_sources = {}
        self._frozen_directives = {}
        self._last_expansion = None
        self._dirty = False

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
        """:return: why the object can't be changed in the draft, None if it can"""
        origin = self._entry(obj).origin
        if origin is None:
            return None
        config_dir = config_root_of(self.device.path)
        part = f"{display_path(origin.file, config_dir)}:{origin.line}"
        return (
            f"It is included from {part} ({describe_includes(origin.includes, config_dir)}). Change it in that file, or the "
            f"vars of the {INCLUDE}."
        )

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
        return self._renderer.template_suggestions(self._entry(obj).component)

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
            self._entry(obj).source[key] = value
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
        component, index = entry.component, entry.index
        directive = self._changed_directive(obj, key, value)
        included, _errors = self._expand_directive(component, index, directive)
        with self.edit(f"Change {key} of the {INCLUDE} at line {self.line_of(obj)}"):
            objects = self._working_objects[component]
            before = [other for other in objects if self._entry(other).is_included and self._entry(other).index == index]
            names = {object_name(other) for other in before}
            self._directives[component][index] = directive
            # the objects of the file see the new instances: before they are rendered
            self._set_draft_sources()
            staying = {_instance_key(self._entry(other).origin): other for other in before}
            result = []
            for expanded in included:
                other = staying.pop(_instance_key(expanded.origin), None)
                if other is None:
                    result.append(
                        self._create_entry(DraftEntry(component, index, expanded.source, 0, expanded.origin, expanded.scope))
                    )
                    continue
                other_entry = self._entry(other)
                other_entry.origin, other_entry.scope = expanded.origin, expanded.scope
                self._render(other)
                result.append(other)
            for removed in staying.values():
                del self._entries[id(removed)]
            position = self._instance_position(component, index, before)
            kept = [other for other in objects if not any(other is old for old in before)]
            self._working_objects[component] = kept[:position] + result + kept[position:]
            self._render_referring(names | {object_name(other) for other in result}, skip=result)
            self._selected_after_edit = [other for other in result if other is obj]

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
            self._entry(obj).source.pop(key)
            self._render(obj)
            self._render_dependents(obj, before)

    def add_object(self, component: str, source: Dict[str, Any]) -> Dict:
        """
        Add an object to the end of a component (it is drawn on top, and saved to the end of the file).
        :return: the rendered object
        """
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
            return self.add_object(entry.component, source)

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
        :param screen: the width and height of the screen
        :return: the rendered objects
        """
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
        for source in prepared:
            if "parentid" in source and source["parentid"] in new_ids:
                source["parentid"] = new_ids[source["parentid"]]
            else:
                source.pop("parentid", None)

        rendered = [self._renderer.render_object(component, source) for source in prepared]
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

        with self.edit(f"Paste {len(prepared)} object{'' if len(prepared) == 1 else 's'}"):
            return [self.add_object(component, source) for source in prepared]

    def remove_object(self, obj: Dict):
        """:raises ReadOnlyObjectError: for an included object"""
        self._check_editable(obj)
        entry = self._entry(obj)
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
        :return: what to change in the source files to save the draft, for every component that has changes
        """
        result = []
        for component in self._components.values():
            component_changes = ComponentChanges(component=component)
            # the directives stay where they are, with their changed `vars` and `for`
            kept: Dict[int, Dict[str, Any]] = dict(self._directives[component.key])
            for index, directive in kept.items():
                removed = set(component.sources[index]) - set(directive)
                if removed:
                    raise AssertionError(f"Removing keys from a directive is not supported: {removed}")
                changed = {key: value for key, value in directive.items() if component.sources[index].get(key) != value}
                if changed:
                    component_changes.changes[index] = copy.deepcopy(changed)
            for obj in self._working_objects[component.key]:
                entry = self._entry(obj)
                if entry.is_included:
                    continue
                if entry.index is None:
                    component_changes.additions.append(copy.deepcopy(entry.source))
                    continue
                kept[entry.index] = entry.source
                original = component.sources[entry.index]
                removed = set(original) - set(entry.source)
                if removed:
                    raise AssertionError(f"Removing properties from a source object is not supported: {removed}")
                changed = {key: value for key, value in entry.source.items() if key not in original or original[key] != value}
                if changed:
                    component_changes.changes[entry.index] = copy.deepcopy(changed)

            component_changes.deletions = set(range(len(component.sources))) - set(kept)
            component_changes.expected_sources = [
                copy.deepcopy(kept[index]) for index in range(len(component.sources)) if index in kept
            ] + component_changes.additions

            if component_changes.changes or component_changes.deletions or component_changes.additions:
                result.append(component_changes)
        return result

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
        self._frozen_directives = {}

        def translate(state: DraftState) -> DraftState:
            def item(key: str, uid: int, index: Optional[int], source, origin, scope) -> DraftItem:
                if key not in rewritten:
                    return uid, index, source, origin, scope
                if origin is None:
                    return uid, new_indices.get(uid), source, origin, scope
                # included: of a directive, which stays in the file
                new = moved[key][index]
                return uid, new, source, _moved_origin(origin, new, lines[key].line_of(new)), scope

            return DraftState(
                objects={key: tuple(item(key, *values) for values in objects) for key, objects in state.objects.items()},
                directives={
                    key: {moved[key][index]: directive for index, directive in directives.items()}
                    if key in rewritten
                    else directives
                    for key, directives in state.directives.items()
                },
            )

        self._history = self._history.mapped(translate)
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

    def _instance_position(self, component: str, index: int, before: List[Dict]) -> int:
        """
        :param before: the objects the directive with this index included so far
        :return: where the objects of the directive go in the objects of the component, without those before
        """
        objects = self._working_objects[component]
        if before:
            return next(position for position, obj in enumerate(objects) if obj is before[0])
        # after the objects before the directive in the file
        return next(
            (
                position
                for position, obj in enumerate(objects)
                if self._entry(obj).index is None or self._entry(obj).index > index
            ),
            len(objects),
        )

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
                    (entry.uid, entry.index, self._frozen_source(entry), entry.origin, entry.scope)
                    for entry in map(self._entry, objects)
                )
                for key, objects in self._working_objects.items()
            },
            directives={
                key: {index: self._frozen_directive(key, index) for index in directives}
                for key, directives in self._directives.items()
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

    def _frozen_source(self, entry: DraftEntry) -> Dict[str, Any]:
        """:return: a copy of the source of an object, the one of the last state if the source didn't change since"""
        frozen = self._frozen_sources.get(entry.uid)
        if frozen is None or frozen != entry.source:
            frozen = copy.deepcopy(entry.source)
            self._frozen_sources[entry.uid] = frozen
        return frozen

    def _differs_from_files(self) -> bool:
        for component in self._components.values():
            if any(directive != component.sources[index] for index, directive in self._directives[component.key].items()):
                return True
            # the included objects follow their directives, which stay
            entries = [entry for entry in map(self._entry, self._working_objects[component.key]) if not entry.is_included]
            indices = [index for index, source in enumerate(component.sources) if not is_directive(source)]
            if len(entries) != len(indices) or any(
                entry.index != index or entry.source != component.sources[index] for index, entry in zip(indices, entries)
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
        for key, items in state.objects.items():
            objects = []
            for uid, index, source, origin, scope in items:
                obj = current.pop(uid, None)
                if obj is None:
                    # an included object shares the object of its part
                    entry = DraftEntry(key, index, source if origin else copy.deepcopy(source), 0, origin, scope)
                    obj = self._create_entry(entry, uid=uid)
                    added.append(obj)
                    objects.append(obj)
                    continue
                entry = self._entry(obj)
                if entry.source != source or entry.origin != origin or entry.scope is not scope:
                    names.add(object_name(obj))
                    pages.add(obj.get("page"))
                    if origin is None:
                        entry.source = copy.deepcopy(source)
                    entry.origin, entry.scope = origin, scope
                    changed.append(obj)
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
        # an included object changes with the scope of its instance
        old = {item[0]: (item[2], item[4]) for objects in before.objects.values() for item in objects}
        new = {item[0]: (item[2], item[4]) for objects in after.objects.values() for item in objects}
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


def _instance_key(origin: ObjectOrigin) -> Tuple[Any, ...]:
    """
    :return: what tells an included object apart from the others of its directive, also after the directive changed: where it
        is written, and the loop values (and the directives in parts) on its way
    """
    steps = tuple(
        (Path(step.file), step.index if position else None, json.dumps(step.loop, sort_keys=True, default=str))
        for position, step in enumerate(origin.includes)
    )
    return Path(origin.file), origin.index, steps


def _moved_origin(origin: ObjectOrigin, index: int, line: int) -> ObjectOrigin:
    """:return: the origin of an included object whose outermost directive is at another index and line of its file"""
    step: IncludeStep = replace(origin.includes[0], index=index, line=line)
    return replace(origin, includes=(step,) + origin.includes[1:])
