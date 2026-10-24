import copy
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, StrictUndefined, TemplateError, TemplateSyntaxError, UndefinedError

from openhasp_config_manager.const import DEVICES_FOLDER_NAME, COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.file_tree import FileNode, scan_file_tree, used_files, used_variable_files
from openhasp_config_manager.gui.domain.plate_session import PlateSession, ComponentSource
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import CmdComponent, JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.device_processor import DeviceProcessor
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor, verify_jsonl_source

_STRICT_JINJA = Environment(undefined=StrictUndefined)

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

    def render_object(self, component: str, source: Dict[str, Any]) -> Dict[str, Any]:
        return self._processor.render_jsonl_object(source, self._vars_of(component))

    def check_template(self, component: str, template: str) -> Optional[str]:
        # a deployment renders unknown variables as they are written (DebugUndefined): check them strictly instead
        try:
            parsed = _STRICT_JINJA.from_string(template)
        except TemplateSyntaxError as ex:
            return f"Invalid template: {ex.message}"
        try:
            parsed.render(self._vars_of(component))
        except UndefinedError as ex:
            return f"Unknown variable: {ex.message}"
        except TemplateError as ex:
            return f"Can't render: {ex.message}"
        return None

    def template_suggestions(self, component: str) -> List[Tuple[str, Any]]:
        if component not in self._suggestions:
            self._suggestions[component] = sorted(flatten_template_variables(self._vars_of(component)))
        return self._suggestions[component]


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
    # the variable files those reference -> the names of the referenced variables (see `used_variable_files`)
    used_variable_files: Dict[Path, List[str]]


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
    used = used_files(device.cmd, device.jsonl)
    return LoadedDevice(
        devices=devices,
        device=device,
        cmd_component=boot_cmd_component,
        jsonl_components=jsonl_components,
        components=components,
        renderer=ProcessorDraftRenderer(device_processor, jsonl_components),
        files=files,
        used_files=used,
        used_variable_files=used_variable_files(files, used, device.path),
    )
