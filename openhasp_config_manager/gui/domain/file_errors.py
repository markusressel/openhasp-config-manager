"""
Explains why a file of a device can't be processed (what a deployment fails on): where the cause is, and how to fix it. An
unknown variable in a variable of the YAML files is reported at that variable, with the devices that have the name, or the
names it may be a typo of. A file that no startup script of the device runs gets a hint that it may not be needed. Qt-free.
"""

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from openhasp_config_manager.const import COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.file_tree import used_files
from openhasp_config_manager.gui.domain.gui_state import relative
from openhasp_config_manager.gui.domain.variables.definitions import VariableDefinitions
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.template_rendering import TemplateRenderError, UnknownVariableError


@dataclass(frozen=True)
class FileError:
    message: str
    # where to fix it: the file that was processed, or the YAML file of the variable that can't be computed
    path: Path
    # starting at 1, None if unknown
    line: Optional[int]
    # how to fix it
    hints: Tuple[str, ...] = ()


def explain_file_error(
    error: Exception,
    file: Path,
    device: Device,
    devices: Sequence[Device],
    config_dir: Path,
    failure: str = "Can't process the file",
) -> FileError:
    """
    :param error: what processing `file` for `device` raised
    :param file: the file that was processed (any file of its folder, for the variables of the folder)
    :param devices: all devices of the config directory, for the variables the others have
    :param failure: what failed, the start of the message if the error can't be traced to a variable
    """
    config_dir = config_dir.resolve()
    file = Path(file).resolve()
    message = f"{failure}: {error}"
    path, line = file, None
    hints: List[str] = []
    if isinstance(error, TemplateRenderError) and error.variable is not None:
        definitions = VariableDefinitions(config_dir)
        definition = definitions.find(error.variable, file, Path(device.path))
        if definition is not None:
            path, line = definition.path, definition.line
            message = str(error)
        if isinstance(error, UnknownVariableError):
            hints += _unknown_variable_hints(error, definitions, file, device, devices, config_dir)
    hints += _unused_file_hints(file, device, config_dir)
    return FileError(message, path, line, tuple(hints))


def _unknown_variable_hints(
    error: UnknownVariableError,
    definitions: VariableDefinitions,
    file: Path,
    device: Device,
    devices: Sequence[Device],
    config_dir: Path,
) -> List[str]:
    others = []
    for other in devices:
        if other.name == device.name:
            continue
        definition = definitions.find(error.unknown, file, Path(other.path))
        if definition is not None:
            others.append(f"{other.name} ({relative(definition.path, config_dir)}:{definition.line})")
    if others:
        where = (
            f"in a YAML file of the folder of {device.name} ({relative(Path(device.path), config_dir)})"
            if file.is_relative_to(config_dir / COMMON_FOLDER_NAME)
            else "in a YAML file that applies to it"
        )
        return [
            f"'{error.unknown}' is defined for {', '.join(others)}, but not for {device.name}. "
            f"Define it for {device.name} too, {where}, or for all devices in a YAML file of the common folder."
        ]
    # names as deep as the unknown one: `common.pages.media` for `common.pages.mediaa`, not `common.pages`
    depth = error.unknown.count(".")
    names = [name for name in _names_for(definitions, file, device) if name.count(".") == depth]
    close = difflib.get_close_matches(error.unknown, names, n=3)
    if close:
        return [f"No YAML file defines '{error.unknown}'. Did you mean {' or '.join(repr(name) for name in close)}?"]
    return [f"No YAML file defines '{error.unknown}': add it to a YAML file, or remove it from '{error.variable}'."]


def _names_for(definitions: VariableDefinitions, file: Path, device: Device) -> List[str]:
    """:return: the variables `file` has on `device`, and the names above them (`a.b` and `a` of `a.b.c`)"""
    names = set()
    for variable_file in definitions.candidates(file, Path(device.path)):
        for leaf in definitions.leaves(variable_file):
            parts = leaf.name.split(".")
            names.update(".".join(parts[: i + 1]) for i in range(len(parts)))
    return sorted(names)


def _unused_file_hints(file: Path, device: Device, config_dir: Path) -> List[str]:
    """A file that no startup script runs may not be needed by the device: it is only deployed since a .cmd file runs it."""
    component = next((c for c in [*device.cmd, *device.jsonl] if Path(c.path).resolve() == file), None)
    if component is None:
        return []
    used = {Path(path).resolve() for path in used_files(device.cmd, device.jsonl, config_dir)}
    if file in used:
        return []
    # the plate's name of the file, e.g. `common_page_wz_content.jsonl`
    runners = [
        relative(Path(cmd.path), config_dir)
        for cmd in device.cmd
        if any(command.split("/")[-1] == component.name for command in cmd.commands)
    ]
    if runners:
        # the same hint for every file the .cmd files run
        return [
            f"No startup script of {device.name} runs {' or '.join(runners)}, but it is deployed with the files it runs "
            f"(every .cmd file is). If {device.name} doesn't need them, delete them, or move them into the folders of the "
            f"devices that use them."
        ]
    return [
        f"No startup script of {device.name} runs {relative(file, config_dir)}. If {device.name} doesn't need it, delete "
        f"it, or move it into the folders of the devices that use it."
    ]
