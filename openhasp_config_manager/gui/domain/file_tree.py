from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import yaml

from openhasp_config_manager.const import COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.plate_session import ComponentSource
from openhasp_config_manager.openhasp_client.model.component import CmdComponent, JsonlComponent
from openhasp_config_manager.processing.template_rendering import referenced_variables


class FileKind(Enum):
    FOLDER = "folder"
    JSONL = "jsonl"
    CMD = "cmd"
    VARIABLES = "variables"


# the scripts the plate runs by itself: at startup, and when the network connects or is lost
STARTUP_SCRIPTS = ["boot.cmd", "online.cmd", "offline.cmd"]

_KINDS = {
    ".jsonl": FileKind.JSONL,
    ".cmd": FileKind.CMD,
    ".yaml": FileKind.VARIABLES,
    ".yml": FileKind.VARIABLES,
}


@dataclass
class FileNode:
    """A folder or a file of the config directory that matters for the pages of a device."""

    name: str
    path: Path
    kind: FileKind
    children: List["FileNode"] = field(default_factory=list)


def config_root_of(device_path: Path) -> Path:
    """:return: the config directory of a device folder (`<config>/devices/<device>`)"""
    return device_path.parent.parent


def scan_file_tree(device_path: Path) -> List[FileNode]:
    """
    The folders of the config directory that hold the files of a device: the config directory itself with its global
    variable files (`theme.yaml`, `global.vars.yaml`, ...; not its subfolders), `common` (if it exists) and the device
    folder, with their subfolders. Only .jsonl, .cmd and variable (.yaml) files are listed, folders without any are
    left out.
    """
    roots = []
    config_root = config_root_of(device_path)
    global_variables = [
        FileNode(name=entry.name, path=entry, kind=FileKind.VARIABLES)
        for entry in sorted(config_root.iterdir(), key=lambda e: e.name)
        if entry.is_file() and not entry.name.startswith(".") and _KINDS.get(entry.suffix) == FileKind.VARIABLES
    ]
    if global_variables:
        roots.append(FileNode(name=config_root.name, path=config_root, kind=FileKind.FOLDER, children=global_variables))
    common = scan_folder(Path(config_root_of(device_path), COMMON_FOLDER_NAME))
    if common is not None:
        roots.append(common)
    device = scan_folder(device_path)
    if device is not None:
        roots.append(device)
    return roots


def scan_folder(path: Path) -> Optional[FileNode]:
    """:return: the folder with its relevant files and subfolders, or None if it has none"""
    if not path.is_dir():
        return None
    entries = sorted((entry for entry in path.iterdir() if not entry.name.startswith(".")), key=lambda e: e.name)
    folders = [node for node in (scan_folder(entry) for entry in entries if entry.is_dir()) if node is not None]
    files = [
        FileNode(name=entry.name, path=entry, kind=_KINDS[entry.suffix])
        for entry in entries
        if entry.is_file() and entry.suffix in _KINDS
    ]
    if not folders and not files:
        return None
    return FileNode(name=path.name, path=path, kind=FileKind.FOLDER, children=folders + files)


def used_files(cmd_components: List[CmdComponent], jsonl_components: List[JsonlComponent]) -> Dict[Path, str]:
    """
    The .cmd and .jsonl files the plate runs: the startup scripts (`STARTUP_SCRIPTS`) and everything they run, directly
    or through other .cmd files.
    :return: the path of each used file -> the startup script that runs it (the first one, if several do)
    """
    cmds = {component.name: component for component in cmd_components}
    jsonls = {component.name: component for component in jsonl_components}
    result: Dict[Path, str] = {}

    def visit(cmd: CmdComponent, script: str):
        if cmd.path in result:
            return
        result[cmd.path] = script
        for command in cmd.commands:
            name = command.split("/")[-1]
            if name.endswith(".jsonl") and name in jsonls:
                result.setdefault(jsonls[name].path, script)
            elif name.endswith(".cmd") and name in cmds:
                visit(cmds[name], script)

    for script in STARTUP_SCRIPTS:
        if script in cmds:
            visit(cmds[script], script)
    return result


def used_variable_files(roots: List[FileNode], used: Iterable[Path], device_path: Path) -> Dict[Path, List[str]]:
    """
    The variable (.yaml) files whose variables the used files reference. A variable file applies to the files in its
    folder and below; the files of the common folder also get the variables of the device folder itself
    (see `DeviceProcessor`). Variables used by the values of other variables count too.
    :param roots: the folders of the device (see `scan_file_tree`)
    :param used: the .cmd and .jsonl files the plate runs (see `used_files`)
    :return: the path of each used variable file -> the names of its variables that are referenced. A file that can't
        be read as YAML counts as used (with no names): better shown than hidden by mistake.
    """
    device_path = device_path.resolve()
    common_path = Path(config_root_of(device_path), COMMON_FOLDER_NAME)
    used = [path.resolve() for path in used]
    references = {path: referenced_variables(path.read_text()) for path in used if path.is_file()}

    variable_files: Dict[Path, Dict[str, Any]] = {}
    unreadable: Dict[Path, List[str]] = {}
    stack = list(roots)
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.kind == FileKind.VARIABLES:
            try:
                content = yaml.safe_load(node.path.read_text())
            except yaml.YAMLError:
                unreadable[node.path.resolve()] = []
                continue
            variable_files[node.path.resolve()] = content if isinstance(content, dict) else {}

    def in_scope(variable_file: Path, path: Path) -> bool:
        folder = variable_file.parent
        return path.is_relative_to(folder) or (path.is_relative_to(common_path) and folder == device_path)

    result: Dict[Path, Set[str]] = {}
    for path, names in references.items():
        visible = {
            variable_file: variables for variable_file, variables in variable_files.items() if in_scope(variable_file, path)
        }
        names = set(names)
        # variables can use other variables: follow their values until nothing new is found
        while True:
            used_here = {
                variable_file: set(variables) & names for variable_file, variables in visible.items() if set(variables) & names
            }
            more = set()
            for variable_file, used_names in used_here.items():
                more |= referenced_variables(yaml.safe_dump({name: visible[variable_file][name] for name in used_names}))
            if more <= names:
                break
            names |= more
        for variable_file, used_names in used_here.items():
            result.setdefault(variable_file, set()).update(used_names)

    return {**{path: sorted(names) for path, names in result.items()}, **unreadable}


def format_pages(pages: Iterable[int]) -> str:
    """:return: the pages as ranges, e.g. "p0, p2–p4" for [0, 2, 3, 4]"""
    ranges = []
    for page in sorted(set(pages)):
        if ranges and page == ranges[-1][1] + 1:
            ranges[-1][1] = page
        else:
            ranges.append([page, page])
    return ", ".join(f"p{start}" if start == end else f"p{start}–p{end}" for start, end in ranges)


def relative_config_path(path: Path, device_path: Path) -> str:
    """:return: the path of a file of a device as it appears in the config directory, e.g. "common/dialog/x.jsonl" """
    try:
        return str(path.resolve().relative_to(config_root_of(device_path).resolve()))
    except ValueError:
        return str(path)


def default_target_component(
    components: List[ComponentSource],
    working_objects: Dict[str, List[Dict]],
    page: int,
) -> Optional[str]:
    """
    Choose the jsonl component new objects of a page go into, when the user did not choose one: the device's own
    file with the most objects on the page (the later one on a tie: it is drawn on top), otherwise its last file.
    A shared file of the common folder only if the device has no files of its own (saving it changes the pages of
    other devices too).
    :return: the key of the component, or None if the draft has no components
    """
    candidates = [component for component in components if not component.is_common] or components
    if not candidates:
        return None

    def objects_on_page(component: ComponentSource) -> int:
        return sum(1 for obj in working_objects.get(component.key, []) if obj.get("page") == page)

    best = max(reversed(candidates), key=objects_on_page)
    if objects_on_page(best) > 0:
        return best.key
    return candidates[-1].key
