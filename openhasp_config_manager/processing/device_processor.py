import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import orjson

from openhasp_config_manager.openhasp_client.model.component import (
    Component,
    JsonlComponent,
    CmdComponent,
    TextComponent,
    RawComponent,
)
from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.jsonl.includes import (
    Expansion,
    ExpandedObject,
    IncludeExpansionError,
    IncludeLookupError,
    IncludedObjectError,
    PartFile,
    directive_paths,
    expand_includes,
)
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import JsonlPreProcessor
from openhasp_config_manager.processing.template_rendering import (
    object_variables,
    render_dict_recursive,
    render_template,
    render_template_or_keep,
    render_variables,
)
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.util import add_missing_keys, merge_dict_into, merge_dict_recursive, merge_dict_shared

# the name of an object in the variables, `p1b2`
_OBJECT_NAME = re.compile(r"p\d+b\d+")


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(
        self,
        device: Device,
        jsonl_object_processors: List[JsonlObjectProcessor],
        variable_manager: VariableManager,
    ):
        self._device = device

        self._jsonl_components: List[JsonlComponent] = []
        self._others: List[Component] = []

        self._jsonl_preprocessor = JsonlPreProcessor()
        self._jsonl_object_processors = jsonl_object_processors
        self._variable_manager = variable_manager
        # path -> its computed variables, see `path_variables`
        self._path_variables: Dict[str, Dict[str, Any]] = {}
        self._dimensions = ObjectDimensionsProcessor()
        # path -> the objects of the file on disk after its directives are replaced, see `expand_jsonl_objects`
        self._expansions: Dict[str, Expansion] = {}
        # path -> the file as a part, see `part`
        self._parts: Dict[str, PartFile] = {}
        # path -> the defaults of a part, see `defaults`
        self._defaults: Dict[str, Dict[str, Any]] = {}
        # resolved path -> a part to include instead of its file, see `set_draft_parts`
        self._draft_parts: Dict[str, PartFile] = {}
        self._part_paths: Optional[Set[Path]] = None
        # the jsonl files the plate runs (resolved), see `set_run_paths`; None: all of them
        self._run_paths: Optional[Set[Path]] = None

    def add_component(self, component: Component):
        if isinstance(component, JsonlComponent):
            self._add_jsonl(component)
        else:
            self._add_other(component)

    def _add_other(self, component: Component):
        self._others.append(component)

    def _add_jsonl(self, component: JsonlComponent):
        self._jsonl_components.append(component)
        self._part_paths = None

    def set_run_paths(self, paths: Iterable[Path]):
        """
        The jsonl files the plate runs (from a .cmd file, or `hasp.pages`). Only their objects (and those of the parts they
        include) are in the object references (`p1b2`) of the others: the plate has no other objects, and the variables of a
        file the device doesn't run (e.g. of a page another device shows) must not break it. Without it, all files count.
        """
        self._run_paths = {Path(path).resolve() for path in paths}

    def normalize(self, device: Device, component: Component) -> str | bytes:
        if isinstance(component, JsonlComponent):
            template_vars: Dict[str, any] = self._compute_jsonl_template_variables(device, component)
            return self._normalize_jsonl(self._device.config, component, template_vars)
        elif isinstance(component, CmdComponent):
            template_vars: Dict[str, any] = {}
            return self._normalize_cmd(self._device.config, component, template_vars)
        elif isinstance(component, TextComponent):
            # no changes necessary
            return component.content
        elif isinstance(component, RawComponent):
            # no changes necessary
            return component.content
        elif isinstance(component, Component):
            raise NotImplementedError(f"Unknown component type: {component.type}")
        else:
            raise AssertionError(f"Received unexpected input: {component}")

    def parse_jsonl_objects(self, component: JsonlComponent) -> List[Dict[str, Any]]:
        """
        Parses the objects of a jsonl component as they are written in the file: comments removed, templates not rendered.
        :param component: the component
        :return: the source objects, in the order of the file
        """
        try:
            return [
                orjson.loads(self._jsonl_preprocessor.cleanup_object_for_json_parsing(ob))
                for ob in self._jsonl_preprocessor.split_jsonl_objects(component.content)
            ]
        except ValueError as ex:
            raise ValueError(f"Invalid JSONL in {component.path}: {ex}") from ex

    @property
    def config_dir(self) -> Path:
        return self._variable_manager.cfg_root

    def expand_jsonl_objects(self, component: JsonlComponent, sources: Optional[List[Dict[str, Any]]] = None) -> Expansion:
        """
        Replace the directives (`!include`) of a jsonl component with the objects they include (see `expand_includes`).
        :param component: the component, which must have been added to this processor
        :param sources: its source objects, to use instead of those in its file (see parse_jsonl_objects)
        :return: the objects of the component in their order, and the errors of its directives
        """
        key = str(component.path)
        if sources is not None:
            return self._expand(component, sources)
        if key not in self._expansions:
            self._expansions[key] = self._expand(component, self.parse_jsonl_objects(component))
        return self._expansions[key]

    def _expand(self, component: JsonlComponent, sources: List[Dict[str, Any]]) -> Expansion:
        return expand_includes(component.path, component.content, sources, self.path_variables(component.path), self)

    def set_draft_parts(self, parts: Dict[Path, PartFile]):
        """
        Include these parts instead of their files (e.g. parts changed in the editor), also in the object references of
        `jsonl_template_variables`. They replace those set before.
        :param parts: path -> the part, whose sources are not changed
        """
        self._draft_parts = {str(Path(path).resolve()): part for path, part in parts.items()}
        # the expansions of the files on disk include the parts
        self._expansions = {}

    def part(self, path: str) -> PartFile:
        """
        :param path: the path of an `!include`, relative to the config directory (or absolute)
        :return: the file, if it is a jsonl file of this device (the draft part, see `set_draft_parts`)
        :raises IncludeLookupError: if it is not
        """
        file = Path(self.config_dir, path)
        key = str(file.resolve())
        if key in self._draft_parts:
            return self._draft_parts[key]
        if key not in self._parts:
            component = next((c for c in self._jsonl_components if str(Path(c.path).resolve()) == key), None)
            if component is None:
                if not file.is_file():
                    raise IncludeLookupError(f"The file to include doesn't exist: {path}")
                raise IncludeLookupError(
                    f"{path} is not a file of the device {self._device.name}: only the files in common/ and in the folder of "
                    f"the device can be included"
                )
            self._parts[key] = PartFile(component.path, component.content, self.parse_jsonl_objects(component))
        return self._parts[key]

    def defaults(self, path: Path) -> Dict[str, Any]:
        """
        :return: the variables of the YAML files of the folders of a part, not computed (see `instance_scope`). Shared by the
            instances: don't change it.
        """
        key = str(path)
        if key not in self._defaults:
            self._defaults[key] = self._variable_manager.get_raw_vars(path)
        return self._defaults[key]

    def part_paths(self) -> Set[Path]:
        """:return: the files that a jsonl component of the device includes (resolved), even if a directive has an error"""
        if self._part_paths is None:
            self._part_paths = {
                Path(self.config_dir, path).resolve()
                for component in self._jsonl_components
                for path in directive_paths(self.parse_jsonl_objects(component))
            }
        return self._part_paths

    def jsonl_template_variables(
        self,
        component: JsonlComponent,
        draft_objects: Optional[Dict[Path, List[Dict[str, Any]]]] = None,
        alone: bool = False,
    ) -> Dict[str, Any]:
        """
        :param component: the component, which must have been added to this processor, unless it is `alone`
        :param draft_objects: component path -> its source objects (see parse_jsonl_objects), to use instead of the
            objects in the files of those components
        :param alone: only the objects of the component are in the object references (`pXbY`), not those of the files of
            the device: for objects that are shown on their own (e.g. a part, see `load_part_alone`). Its objects must be in
            `draft_objects`.
        :return: the variables the templates of the component's objects are rendered with
        """
        return self._compute_jsonl_template_variables(self._device, component, draft_objects, alone=alone)

    def render_jsonl_object(
        self,
        source_object: Dict[str, Any],
        template_vars: Dict[str, Any],
        keep_unresolved: bool = False,
        scope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Renders one source object like a deployment does: its templates, then the object processors
        (percentages, value types, theme defaults).
        :param source_object: the object as written in the file (see parse_jsonl_objects), it is not modified
        :param template_vars: the variables of its component (see jsonl_template_variables)
        :param keep_unresolved: keep a value as written if it uses a variable that doesn't exist, instead of failing (for the
            editor, which shows objects with mistakes; a deployment fails)
        :param scope: the variables of the instance of a part, for an included object (see `ExpandedObject.scope`)
        :return: the rendered object
        """
        if scope:
            template_vars = {**template_vars, **scope}
        render = render_template_or_keep if keep_unresolved else render_template

        def rendered(key: str) -> Any:
            value = source_object.get(key, "0")
            return render(value, template_vars) if isinstance(value, str) else value

        # `this` and `bY` (see `object_variables`): the page and the id say which object it is
        name = f"p{rendered('page')}b{rendered('id')}"
        object_vars = {**template_vars, **object_variables(name, template_vars)}
        normalized_object = {}
        for key, value in source_object.items():
            if isinstance(value, str):
                normalized_object[key] = render(value, object_vars)
            else:
                normalized_object[key] = value

        processed = normalized_object
        for processor in self._jsonl_object_processors:
            processed = processor.process(processed, self._device.config, template_vars)
        return processed

    def _normalize_jsonl(self, config: Config, component: JsonlComponent, template_vars: Dict[str, any]) -> str:
        """
        :raises IncludeExpansionError: if a directive has an error
        :raises IncludedObjectError: if an object of a part can't be rendered
        """
        expansion = self.expand_jsonl_objects(component)
        if expansion.errors:
            raise IncludeExpansionError(expansion.errors, self.config_dir)
        return "\n".join(json.dumps(self._render_expanded(obj, template_vars), indent=None) for obj in expansion.objects)

    def expand_sources(self, file: Path, sources: List[Dict[str, Any]]) -> Expansion:
        """
        Replace the directives of objects that are not in a file of the device (e.g. a page defined in code, see
        `openhasp_config_manager.model`), as if they were the objects of a jsonl file at `file`: its variables are those of
        that path (see `path_variables`), its lines those of one object per line.
        :param file: a path in the config directory, which doesn't have to exist
        :param sources: the objects, as written in a file (see parse_jsonl_objects)
        :return: the objects in their order, and the errors of the directives (see `expand_includes`)
        """
        return self.expand_jsonl_objects(self._source_component(file, sources), sources)

    def render_sources(
        self, file: Path, sources: List[Dict[str, Any]], replaced_page: Optional[int] = None
    ) -> List[Tuple[ExpandedObject, Dict[str, Any]]]:
        """
        Renders objects that are not in a file of the device like the objects of a file at `file` are rendered on a
        deployment (see `expand_sources`): the object references (`pXbY`, `bY`, `this`) see the objects of the files of the
        device and these objects, every object goes through the templates and the object processors.
        :param replaced_page: a page these objects replace on the plate (e.g. a page that is cleared and pushed): the
            objects of the files of the device on that page are not in the object references, so `bY` is one of `sources`
        :return: every object after the directives are replaced, with its rendered object
        :raises IncludeExpansionError: if a directive has an error
        :raises IncludedObjectError: if an object of a part can't be rendered
        """
        component = self._source_component(file, sources)
        expansion = self.expand_jsonl_objects(component, sources)
        if expansion.errors:
            raise IncludeExpansionError(expansion.errors, self.config_dir)
        template_vars = self._compute_jsonl_template_variables(
            self._device, component, {component.path: sources}, replaced_page
        )
        return [(obj, self._render_expanded(obj, template_vars)) for obj in expansion.objects]

    @staticmethod
    def _source_component(file: Path, sources: List[Dict[str, Any]]) -> JsonlComponent:
        """A component for objects that are in no file: one object per line, so the lines of its errors are the objects."""
        content = "\n".join(json.dumps(source) for source in sources)
        return JsonlComponent(name=Path(file).name, type="jsonl", path=Path(file), content=content)

    def _render_expanded(self, obj: ExpandedObject, template_vars: Dict[str, Any]) -> Dict[str, Any]:
        if not obj.origin.is_included:
            return self.render_jsonl_object(obj.source, template_vars)
        try:
            return self.render_jsonl_object(obj.source, template_vars, scope=obj.scope)
        except Exception as ex:
            raise IncludedObjectError(obj.origin, self.config_dir, str(ex)) from ex

    def _normalize_cmd(self, _device_config, component: CmdComponent, template_vars: Dict[str, any]) -> str:
        return render_template(component.content, template_vars)

    def _compute_jsonl_template_variables(
        self,
        device: Device,
        component: Component,
        draft_objects: Optional[Dict[Path, List[Dict[str, Any]]]] = None,
        replaced_page: Optional[int] = None,
        alone: bool = False,
    ) -> Dict[str, Any]:
        """
        Computes a map of "variable" -> "evaluated value in the given path context" for the given component.

        :param component: the component to use as a context for evaluating template variables; one that was not added to
            this processor (see `render_sources`) needs its objects in `draft_objects`
        :param replaced_page: leaves the objects of the other components on this page out (see `render_sources`)
        :param alone: leaves the objects of the other components out (see `jsonl_template_variables`)
        :return: map of "variable" -> "evaluated value in the given path context"
        """
        result = {}

        # object specific variables for all components that the processor currently knows about, the component itself last
        sorted_components = [] if alone else [c for c in self._jsonl_components if c != component]
        sorted_components.append(component)
        part_paths = self.part_paths()
        if component not in self._jsonl_components:
            # the parts of objects that are in no file only count through them, like the parts of the files
            part_paths = part_paths | {
                Path(self.config_dir, path).resolve() for path in directive_paths(draft_objects[component.path])
            }
        for c in sorted_components:
            # the objects of a part are in the variables through the files that include it (and its own when it is rendered)
            if c != component and Path(c.path).resolve() in part_paths:
                continue
            if c != component and self._run_paths is not None and Path(c.path).resolve() not in self._run_paths:
                continue
            component_template_vars = self.path_variables(c.path)

            if draft_objects is not None and c.path in draft_objects:
                expansion = self.expand_jsonl_objects(c, draft_objects[c.path])
            else:
                expansion = self.expand_jsonl_objects(c)
            c_result, scopes = self._object_map(expansion.objects)
            # `result` becomes what the variables of this component start with: everything before it, and its own variables
            merge_dict_into(result, component_template_vars)

            def entry_vars(name: str, template_vars: Dict[str, Any], scopes=scopes) -> Dict[str, Any]:
                return {**scopes.get(name, {}), **object_variables(name, template_vars)}

            rendered_template_vars = render_dict_recursive(
                input=c_result,
                template_vars=merge_dict_shared(result, c_result),
                convert=self._object_value,
                entry_vars=entry_vars,
            )
            if replaced_page is not None and c != component:
                rendered_template_vars = {
                    name: value
                    for name, value in rendered_template_vars.items()
                    if not (_OBJECT_NAME.fullmatch(name) and name.startswith(f"p{replaced_page}b"))
                }
            # what the objects add, without overriding anything
            add_missing_keys(result, rendered_template_vars)

        if result is None:
            raise AssertionError("Unexpected None value")
        return result

    def _object_value(self, keys: List[str], value: Any) -> Any:
        """The properties of the objects in the variables (`p1b2.w`) are numbers and pixels, as they are sent to the plate."""
        if len(keys) == 2 and _OBJECT_NAME.fullmatch(keys[0]):
            return self._dimensions.normalize_value(keys[1], value, self._device.config)
        return value

    def path_variables(self, path: Path) -> Dict[str, Any]:
        """
        :param path: a file or folder of the config directory
        :return: the variables of the YAML files for that path on this device, computed (see `render_variables`), and `device`.
            A file of the common folder also gets the variables of the device folder. Shared: don't change it.
        :raises TemplateRenderError: if a variable can't be computed
        """
        key = str(path)
        if key not in self._path_variables:
            variables = self._variable_manager.get_raw_vars(path)
            if "/common/" in key:
                # for common components, also include device specific, top-level variables
                variables = merge_dict_recursive(variables, self._variable_manager.get_raw_vars(self._device.path))
            device = self._device.config.openhasp_config_manager.device
            self._path_variables[key] = {**render_variables(variables, {"device": device}), "device": device}
        return self._path_variables[key]

    def _object_map(self, objects: List[ExpandedObject]) -> Tuple[Dict[str, dict], Dict[str, Dict[str, Any]]]:
        """
        :return: "p<page>b<id>" -> the source object, and the name of an included object -> the variables of its instance
        """
        sources: Dict[str, dict] = {}
        scopes: Dict[str, Dict[str, Any]] = {}
        for obj in objects:
            name = obj.name or self._compute_object_key(obj.source)
            sources[name] = obj.source
            if obj.origin.is_included:
                scopes[name] = obj.scope
            else:
                scopes.pop(name, None)
        return sources, scopes

    @staticmethod
    def _compute_object_key(jsonl_object: Dict) -> str:
        return f"p{jsonl_object.get('page', '0')}b{jsonl_object.get('id', '0')}"
