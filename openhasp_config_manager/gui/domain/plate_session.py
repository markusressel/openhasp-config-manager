import copy
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Optional, Any, Protocol, Set, Tuple

from jinja2 import TemplateError

from openhasp_config_manager.gui.domain.page_objects import next_free_id
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.template_rendering import has_nested_templates, referenced_objects
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor, NUMERIC_PROPERTY_NAMES
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor

_NUMERIC_PROPERTY = re.compile(NUMERIC_PROPERTY_NAMES)


class DraftRenderer(Protocol):
    """
    Renders source objects like a deployment does (see DeviceProcessor), with the template variables of their component.
    """

    def render_object(self, component: str, source: Dict[str, Any]) -> Dict[str, Any]: ...

    def set_draft_sources(self, sources: Dict[str, List[Dict[str, Any]]]):
        """Templates that refer to other objects (`{{ p1b2.x }}`) see these source objects, per component key."""
        ...

    def check_template(self, component: str, template: str) -> Optional[str]:
        """:return: why the template can't be rendered, or None if it can"""
        ...

    def template_suggestions(self, component: str) -> List[Tuple[str, Any]]:
        """:return: (template, its current value) for the variables available in the component"""
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
class _Entry:
    component: str
    # the index of the object in the source file, None for objects added in the draft
    index: Optional[int]
    # the object as written in the source file (with templates), changed by the draft
    source: Dict[str, Any]


@dataclass
class ComponentChanges:
    component: ComponentSource
    # index in the source file -> properties to set
    changes: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    deletions: Set[int] = field(default_factory=set)
    additions: List[Dict[str, Any]] = field(default_factory=list)
    # the source objects the file must have after the changes
    expected_sources: List[Dict[str, Any]] = field(default_factory=list)


def _has_template(source: Dict[str, Any]) -> bool:
    return any(isinstance(value, str) and "{{" in value for value in source.values())


# stands for every object: the objects a template refers to can't be told
ANY_OBJECT = "*"


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
    """

    def __init__(self, device: Device):
        self.device = device
        self._components: OrderedDict[str, ComponentSource] = OrderedDict()
        self._renderer: Optional[DraftRenderer] = None
        self._working_objects: OrderedDict[str, List[Dict]] = OrderedDict()
        # id(rendered object) -> its source
        self._entries: Dict[int, _Entry] = {}
        self._loaded = False

        # Track if the UI has modified the draft
        self.is_dirty: bool = False

    def load(self, components: List[ComponentSource], renderer: DraftRenderer):
        """Initializes the draft from the components as they are on disk."""
        self._components = OrderedDict((component.key, component) for component in components)
        self._renderer = renderer
        self.reset_to_disk()
        self._loaded = True

    def reset_to_disk(self):
        """Discards all changes of the draft. The rendered objects are new objects afterwards."""
        self._working_objects = OrderedDict()
        self._entries = {}
        self._renderer.set_draft_sources({component.key: component.sources for component in self._components.values()})
        for component in self._components.values():
            self._working_objects[component.key] = [
                self._create(component.key, index, copy.deepcopy(source)) for index, source in enumerate(component.sources)
            ]
        self.is_dirty = False

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
        """:return: the line (starting at 1) on which the object starts in its source file, None for an object added in the draft"""
        index = self.source_index(obj)
        return None if index is None else _source_editor(self.component_of(obj).content).line_of(index)

    def component_at(self, path: Path) -> Optional[ComponentSource]:
        """:return: the component of a file (the path in any spelling), None if the draft has no objects of that file"""
        resolved = path.resolve()
        return next((component for component in self._components.values() if component.path.resolve() == resolved), None)

    def object_of_source(self, component: str, index: int) -> Optional[Dict]:
        """:return: the rendered object that was written as the n-th object of a component's file, None if it was deleted"""
        return next(
            (obj for obj in self._working_objects.get(component, []) if self._entry(obj).index == index),
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
        return self._renderer.check_template(self._entry(obj).component, template)

    def template_suggestions(self, obj: Dict) -> List[Tuple[str, Any]]:
        return self._renderer.template_suggestions(self._entry(obj).component)

    def variable_names(self, component: str) -> List[str]:
        """:return: the names of the template variables a file can use, e.g. "theme.navbar.height" """
        return [template[3:-3] for template, _value in self._renderer.template_suggestions(component)]

    # --- editing ---

    def check_value(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        """
        Check a value for a property, as written in the source (a literal or a template), before setting it.
        :return: why it can't be set, or None if it can
        """
        try:
            rendered = self._render_with(obj, key, value)
        except TemplateError as ex:
            return f"Invalid template: {ex.message}"
        result = rendered.get(key)
        if _NUMERIC_PROPERTY.fullmatch(key) and not isinstance(result, (int, float)):
            return f"Must be a number, renders to {result!r}."
        return None

    def set_source_value(self, obj: Dict, key: str, value: Any):
        """
        Set a property as it is written in the source, a literal or a template, and render the object again.
        Nothing changes if the object can't be rendered with it (see check_value).
        """
        before = object_name(obj)
        rendered = self._render_with(obj, key, value)
        self._entry(obj).source[key] = value
        self._apply(obj, rendered)
        self._render_dependents(obj, before)

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
        for key in ("x", "y"):
            if self.is_template(obj, key) or self.is_percentage(obj, key):
                self.set_source_value(obj, key, obj.get(key, 0))

    def remove_source_value(self, obj: Dict, key: str):
        """
        Remove a property the draft added to the source (e.g. resetting a theme default that was changed),
        and render the object again.
        """
        before = object_name(obj)
        self._entry(obj).source.pop(key)
        self._render(obj)
        self._render_dependents(obj, before)

    def add_object(self, component: str, source: Dict[str, Any]) -> Dict:
        """
        Add an object to the end of a component (it is drawn on top, and saved to the end of the file).
        :return: the rendered object
        """
        obj = self._create(component, None, copy.deepcopy(source))
        self._working_objects[component].append(obj)
        self.is_dirty = True
        self._render_dependents(obj)
        return obj

    def duplicate_object(self, obj: Dict, offset: int = 10) -> Dict:
        """
        Duplicate an object into the same component, with the next free id on its page, moved by `offset`.
        Templates of the original are kept, except for the moved position.
        :return: the rendered duplicate
        """
        entry = self._entry(obj)
        source = copy.deepcopy(entry.source)
        source["id"] = next_free_id(self._working_objects, obj.get("page", 0))
        source["x"] = obj.get("x", 0) + offset
        source["y"] = obj.get("y", 0) + offset
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

        return [self.add_object(component, source) for source in prepared]

    def remove_object(self, obj: Dict):
        entry = self._entry(obj)
        objects = self._working_objects[entry.component]
        objects.pop(next(i for i, other in enumerate(objects) if other is obj))
        del self._entries[id(obj)]
        self.is_dirty = True
        self._render_dependents(obj)

    # --- saving ---

    def changes(self) -> List[ComponentChanges]:
        """
        :return: what to change in the source files to save the draft, for every component that has changes
        """
        result = []
        for component in self._components.values():
            component_changes = ComponentChanges(component=component)
            kept: Dict[int, Dict[str, Any]] = {}
            for obj in self._working_objects[component.key]:
                entry = self._entry(obj)
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

    # --- internals ---

    def _create(self, component: str, index: Optional[int], source: Dict[str, Any]) -> Dict:
        obj = self._renderer.render_object(component, source)
        self._entries[id(obj)] = _Entry(component=component, index=index, source=source)
        return obj

    def _render(self, obj: Dict):
        entry = self._entry(obj)
        self._apply(obj, self._renderer.render_object(entry.component, entry.source))

    def _render_dependents(self, changed: Dict, name_before: Optional[str] = None):
        """
        Render the objects with templates again, after the source of `changed` changed (or it was added or removed):
        templates can refer to other objects (`{{ p1b2.x }}`). Only the objects that refer to `changed` are rendered, which
        matters: the variables of a component are expensive to compute.
        :param name_before: the name of `changed` (`p1b2`) before the change, if the change could rename it
        """
        self._renderer.set_draft_sources(
            {key: [self._entry(obj).source for obj in objects] for key, objects in self._working_objects.items()}
        )
        names = {object_name(changed)} | ({name_before} if name_before else set())
        names_or_any = names | {ANY_OBJECT}
        for objects in self._working_objects.values():
            for obj in objects:
                entry = self._entry(obj)
                if obj is not changed and self._references_of(entry) & names_or_any:
                    rendered = self._renderer.render_object(entry.component, entry.source)
                    if rendered != obj:
                        self._apply(obj, rendered)

    def _references_of(self, entry: _Entry) -> Set[str]:
        """:return: the objects the templates of an object refer to (`ANY_OBJECT` if that can't be told)"""
        values = [value for value in entry.source.values() if isinstance(value, str)]
        if any(has_nested_templates(value) for value in values):
            # the names are built by templates, which need the variables of the component
            return self._renderer.referenced_objects(entry.component, entry.source)
        return set().union(*(referenced_objects(value, {}) for value in values))

    def _render_with(self, obj: Dict, key: str, value: Any) -> Dict:
        """:return: the object rendered with a different source value, without changing it"""
        entry = self._entry(obj)
        return self._renderer.render_object(entry.component, {**entry.source, key: value})

    def _apply(self, obj: Dict, rendered: Dict):
        # the preview holds the rendered dict: keep its identity
        obj.clear()
        obj.update(rendered)
        self.is_dirty = True

    def _entry(self, obj: Dict) -> _Entry:
        return self._entries[id(obj)]
