import copy
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openhasp_config_manager.const import DEVICES_FOLDER_NAME, COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.file_tree import FileNode, including_files, scan_file_tree, used_files
from openhasp_config_manager.gui.domain.variables.unused import UnusedVariables, find_unused_variables
from openhasp_config_manager.gui.domain.variables.usages import DeviceFiles, VariableUsages
from openhasp_config_manager.gui.domain.draft.model import ComponentSource
from openhasp_config_manager.gui.domain.draft.session import ANY_OBJECT, PlateSession
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import CmdComponent, JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.device_processor import DeviceProcessor
from openhasp_config_manager.processing.jsonl.includes import Expansion, PartFile
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor, verify_jsonl_source
from openhasp_config_manager.processing.template_rendering import (
    check_template,
    object_variables,
    referenced_objects,
    render_template_or_keep,
)

# how deep nested variables are offered as suggestions
_MAX_SUGGESTION_DEPTH = 6


class ProcessorDraftRenderer:
    """
    Renders the objects of a draft with the DeviceProcessor of a deployment, so the editor shows what a deployment
    would send, and suggests the template variables a deployment would provide.
    """

    def __init__(self, processor: DeviceProcessor, components: List[JsonlComponent]):
        """
        :param components: the jsonl components of the draft, in the order of the deployment
        """
        self._processor = processor
        self._components = {str(component.path): component for component in components}
        # component key -> the template variables of the component, computed when needed
        self._template_var_cache: Dict[str, Dict[str, Any]] = {}
        # component path -> its source objects in the draft, None while the objects are those on disk
        self._draft_objects: Optional[Dict[Path, List[Dict[str, Any]]]] = None
        self._suggestions: Dict[str, List[Tuple[str, Any]]] = {}
        self._references: Dict[Tuple[str, str], Set[str]] = {}

    def set_draft_sources(self, sources: Dict[str, List[Dict[str, Any]]]):
        # templates like `{{ p1b2.x }}` refer to the objects as they are in the draft
        self._draft_objects = {self._components[key].path: copy.deepcopy(objects) for key, objects in sources.items()}
        self._template_var_cache = {}
        self._suggestions = {}

    def _vars_of(self, key: str) -> Dict[str, Any]:
        if key not in self._template_var_cache:
            self._template_var_cache[key] = self._processor.jsonl_template_variables(
                self._components[key], self._draft_objects
            )
        return self._template_var_cache[key]

    def render_object(self, component: str, source: Dict[str, Any], scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._processor.render_jsonl_object(source, self._vars_of(component), keep_unresolved=True, scope=scope)

    def expand_objects(self, component: str, sources: List[Dict[str, Any]]) -> Expansion:
        return self._processor.expand_jsonl_objects(self._components[component], sources)

    def set_draft_parts(self, parts: Dict[Path, PartFile]):
        self._processor.set_draft_parts(parts)
        self._template_var_cache = {}
        self._suggestions = {}

    def part_source(self, path: Path) -> ComponentSource:
        """:return: a part as it is on disk, as a component of the draft (its key is its path)"""
        part = self._processor.part(str(path))
        common_dir = Path(self._processor.config_dir, COMMON_FOLDER_NAME).resolve()
        return ComponentSource(
            key=str(part.path),
            path=Path(part.path),
            content=part.content,
            is_common=Path(part.path).resolve().is_relative_to(common_dir),
            sources=part.sources,
        )

    def referenced_objects(
        self, component: str, source: Dict[str, Any], page: Any = None, scope: Optional[Dict[str, Any]] = None
    ) -> Set[str]:
        """
        :param page: the page of the object, for the objects of its page it names without a page (`b2`)
        :param scope: the variables of the instance of a part, for an included object
        :return: the objects (`p1b2`) the templates of a source object refer to, also when the name is built by a template inside
            of the template (`{{ p{{ page.index }}b2.x }}`), which is resolved with the variables of the component.
            `ANY_OBJECT` if that is not possible. Remembered for the whole session: the inner templates are the same for as long
            as the source is (they are about the layout of the pages, not about the objects). Not for included objects: their
            inner templates depend on their instance.
        """
        if scope:
            return self._referenced_objects(source, {**self._vars_of(component), **scope}, page)
        key = (component, json.dumps(source, sort_keys=True, default=str), str(page))
        if key not in self._references:
            self._references[key] = self._referenced_objects(source, self._vars_of(component), page)
        return self._references[key]

    @staticmethod
    def _referenced_objects(source: Dict[str, Any], variables: Dict[str, Any], page: Any) -> Set[str]:
        names: Set[str] = set()
        for value in source.values():
            if isinstance(value, str):
                found = referenced_objects(value, variables, page)
                if found is None:
                    return {ANY_OBJECT}
                names |= found
        return names

    def check_template(
        self, component: str, template: str, name: Optional[str] = None, scope: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        :param name: the object the template is in (`p1b2`), for `this` and `bY` (see `object_variables`)
        :param scope: the variables of the instance of a part, for an included object
        :return: why the template can't be rendered, or None if it can
        """
        variables = self._vars_of(component)
        if scope:
            variables = {**variables, **scope}
        if name is not None:
            variables = {**variables, **object_variables(name, variables)}
        return check_template(template, variables)

    def variable_value(self, component: str, name: str) -> Any:
        """:return: the value of a template variable (`common.header.bar.height`) in a component :raises KeyError: if it has none"""
        return _variable_value(self._vars_of(component), name)

    def render_text(self, component: str, text: str) -> str:
        """:return: a text with templates the way a deployment renders it (unknown variables stay as written) :raises TemplateError:"""
        return render_template_or_keep(text, self._vars_of(component))

    def path_variable_value(self, path: Path, name: str) -> Any:
        """
        :return: the value of a variable of the YAML files for a file that has no objects in the draft (e.g. a variable file), as
            the device sees it :raises KeyError: if it has none
        """
        return _variable_value(self._processor.path_variables(path), name)

    def render_path_text(self, path: Path, text: str) -> str:
        """:return: a text with templates, rendered with the variables of a file that has no objects in the draft"""
        return render_template_or_keep(text, self._processor.path_variables(path))

    def template_suggestions(self, component: str, scope: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Any]]:
        """:param scope: the variables of the instance of a part, for an included object"""
        if scope:
            return sorted(flatten_template_variables({**self._vars_of(component), **scope}))
        if component not in self._suggestions:
            self._suggestions[component] = sorted(flatten_template_variables(self._vars_of(component)))
        return self._suggestions[component]


def _variable_value(variables: Dict[str, Any], name: str) -> Any:
    """:raises KeyError: if the variables have no such name"""
    value: Any = variables
    for part in name.split("."):
        if dataclasses.is_dataclass(value) and not isinstance(value, type) and hasattr(value, part):
            value = getattr(value, part)
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(name)
    return value


def flatten_template_variables(variables: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """
    :return: ("{{ a.b.c }}", value) for every leaf value of the (nested) variables
    """
    result = []

    def visit(value: Any, path: List[str]):
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
        if isinstance(value, dict):
            if len(path) >= _MAX_SUGGESTION_DEPTH:
                return
            for key, child in value.items():
                # other keys can't be written with dots
                if isinstance(key, str) and key.isidentifier():
                    visit(child, path + [key])
        elif path and isinstance(value, (str, int, float, bool)):
            result.append((f"{{{{ {'.'.join(path)} }}}}", value))

    visit(variables, [])
    return result


class SaveConflictError(Exception):
    pass


@dataclass(frozen=True)
class FileChange:
    path: Path
    content: str
    is_common: bool


def plan_save(session: PlateSession) -> List[FileChange]:
    """
    Compute the new content of every source file the draft changed. Nothing is written.
    :raises SaveConflictError: if a file changed on disk since the draft was loaded
    """
    result = []
    for component_changes in session.changes():
        component = component_changes.component
        content = component.path.read_text()
        if content != component.content:
            raise SaveConflictError(
                f"{component.path} changed on disk since it was loaded. Revert the draft to load it again."
            )
        new_content = JsonlSourceEditor(content).apply(
            changes=component_changes.changes,
            deletions=component_changes.deletions,
            additions=component_changes.additions,
        )
        verify_jsonl_source(new_content, component_changes.expected_sources)
        result.append(FileChange(path=component.path, content=new_content, is_common=component.is_common))
    return result


def write_save(changes: List[FileChange]):
    for change in changes:
        change.path.write_text(change.content)


# the cmd component whose pages the editor shows
BOOT_CMD = "boot.cmd"


@dataclass
class LoadedDevice:
    devices: List[Device]
    device: Device
    cmd_component: CmdComponent
    jsonl_components: List[JsonlComponent]
    # the jsonl components as written on disk, and how to render them, to load a draft
    components: List[ComponentSource]
    renderer: ProcessorDraftRenderer
    # the folders with the files of the device, for the file tree
    files: List[FileNode]
    # the .cmd and .jsonl files the plate runs -> the startup script that runs them (see `used_files`)
    used_files: Dict[Path, str]
    # the parts -> the files that include them (see `including_files`)
    includers: Dict[Path, List[Path]]
    # the parts of the device -> (device, file) of every file of all devices that includes them, for what saving a part changes
    part_includers: Dict[Path, List[Tuple[str, Path]]]
    # where the variables of the YAML files are used, by all devices
    variable_usages: VariableUsages
    # the variable files the device uses -> the names of the variables (see `VariableUsages.used_names`)
    used_variable_files: Dict[Path, List[str]]
    # the variables of the YAML files that no file of any device uses (see `find_unused_variables`)
    unused_variables: Dict[Path, UnusedVariables]


def load_device(config_manager: ConfigManager, name: str) -> LoadedDevice:
    """
    Analyze the config directory again (to reflect changes on disk) and load the pages of a device.
    Runs in a worker thread: it renders templates and must not block the UI.
    """
    devices = config_manager.analyze()
    device = next((d for d in devices if d.name == name), None)
    if device is None:
        raise RuntimeError(f"The device '{name}' no longer exists in {Path(config_manager.cfg_root, DEVICES_FOLDER_NAME)}.")
    return load_analyzed_device(config_manager, devices, device)


def load_analyzed_device(config_manager: ConfigManager, devices: List[Device], device: Device) -> LoadedDevice:
    """Load the pages of a device of the devices that `config_manager.analyze()` returned."""
    relevant_components = config_manager.find_relevant_components(device)
    boot_cmd_component: Optional[CmdComponent] = next((c for c in relevant_components if c.name == BOOT_CMD), None)
    if boot_cmd_component is None:
        raise RuntimeError(f"{device.path} has no {BOOT_CMD}. The editor shows the pages that {BOOT_CMD} loads.")

    jsonl_components = config_manager.determine_device_jsonl_component_order_for_cmd(
        device=device,
        cmd_component=boot_cmd_component,
    )

    device_processor = config_manager.create_device_processor(device)
    common_dir = Path(config_manager.cfg_root, COMMON_FOLDER_NAME)
    components = []
    for jsonl_component in jsonl_components:
        # names can repeat in different folders, paths can't
        key = str(jsonl_component.path)
        components.append(
            ComponentSource(
                key=key,
                path=jsonl_component.path,
                content=jsonl_component.content,
                is_common=jsonl_component.path.is_relative_to(common_dir),
                sources=device_processor.parse_jsonl_objects(jsonl_component),
            )
        )

    files = scan_file_tree(device.path)
    used = used_files(device.cmd, device.jsonl, config_manager.cfg_root)
    includers = including_files(device.jsonl, config_manager.cfg_root)
    part_includers: Dict[Path, List[Tuple[str, Path]]] = {part: [] for part in includers}
    for other in devices:
        for part, paths in including_files(other.jsonl, config_manager.cfg_root).items():
            if part in part_includers:
                part_includers[part] += [
                    (other.name, path) for path in paths if (other.name, path) not in part_includers[part]
                ]
    variable_usages = VariableUsages(
        config_manager.cfg_root,
        [DeviceFiles(d.path, list(used_files(d.cmd, d.jsonl, config_manager.cfg_root))) for d in devices],
    )
    return LoadedDevice(
        devices=devices,
        device=device,
        cmd_component=boot_cmd_component,
        jsonl_components=jsonl_components,
        components=components,
        renderer=ProcessorDraftRenderer(device_processor, jsonl_components),
        files=files,
        used_files=used,
        includers=includers,
        part_includers=part_includers,
        variable_usages=variable_usages,
        used_variable_files=variable_usages.used_names(device.path),
        unused_variables=find_unused_variables(variable_usages),
    )
