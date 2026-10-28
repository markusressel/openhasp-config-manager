from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional


from openhasp_config_manager.const import COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.draft.model import ComponentSource
from openhasp_config_manager.manager import CONFIG_FILE_NAME
from openhasp_config_manager.openhasp_client.model.component import CmdComponent, JsonlComponent


class FileKind(Enum):
    FOLDER = "folder"
    JSONL = "jsonl"
    CMD = "cmd"
    VARIABLES = "variables"
    # the `config.json` of a device: the settings of the plate
    CONFIG = "config"


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
    folder, with their subfolders. Only .jsonl, .cmd and variable (.yaml) files are listed, and the `config.json` of the
    device folder; folders without any are left out.
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
    device = scan_folder(device_path, with_config=True)
    if device is not None:
        roots.append(device)
    return roots


def scan_folder(path: Path, with_config: bool = False) -> Optional[FileNode]:
    """
    :param with_config: whether the folder is a device folder, whose `config.json` is listed too
    :return: the folder with its relevant files and subfolders, or None if it has none
    """
    if not path.is_dir():
        return None
    entries = sorted((entry for entry in path.iterdir() if not entry.name.startswith(".")), key=lambda e: e.name)
    folders = [node for node in (scan_folder(entry) for entry in entries if entry.is_dir()) if node is not None]
    files = [
        FileNode(name=entry.name, path=entry, kind=kind)
        for entry in entries
        if entry.is_file() and (kind := _kind_of(entry, with_config)) is not None
    ]
    if not folders and not files:
        return None
    return FileNode(name=path.name, path=path, kind=FileKind.FOLDER, children=folders + files)


def _kind_of(file: Path, with_config: bool) -> Optional[FileKind]:
    if with_config and file.name == CONFIG_FILE_NAME:
        return FileKind.CONFIG
    return _KINDS.get(file.suffix)


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
