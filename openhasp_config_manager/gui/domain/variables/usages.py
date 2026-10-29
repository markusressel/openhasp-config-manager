"""
Where the variables of the YAML files are used, by the plates of all devices. A variable is used if a template of a file the plate
runs names it (`{{ common.header.height }}`, or a part of it: `{{ common.header }}` uses everything below), if the value of a used
variable names it, or if it is the theme of the type of an object (`theme.obj.btn`, applied without a template). A part
(`!include`) sees the variables of the files that include it too, so its names are looked up from each of them as well. Variables the
manager reads itself (`include_files`, `binary_images`) are used. What other code reads from the files (e.g. a controller that
loads `theme.yaml`) is not known. Qt-free.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Set, Tuple

from openhasp_config_manager.gui.domain.variables.definitions import VariableDefinitions, VariableLeaf
from openhasp_config_manager.gui.domain.variables.references import scan_text
from openhasp_config_manager.manager import BINARY_IMAGES_VARIABLE, INCLUDE_FILES_VARIABLE
from openhasp_config_manager.processing.jsonl.includes import included_paths

# the variables the manager reads itself, by their top-level name
MANAGER_VARIABLES = frozenset({INCLUDE_FILES_VARIABLE, BINARY_IMAGES_VARIABLE})


@dataclass(frozen=True, order=True)
class Usage:
    """Where a variable is used: a template, or the type of an object that gets the theme of its type."""

    path: Path
    # starting at 1, and at 0
    line: int
    column: int
    length: int


@dataclass(frozen=True)
class DeviceFiles:
    """The files the plate of a device runs (its startup scripts and everything they run)."""

    # the folder of the device
    path: Path
    files: List[Path]


# the variables a file names, with where, and the properties of the object that replace what the variable gives it (an object
# that sets `bg_color` itself doesn't use `theme.obj.btn.bg_color`)
_Named = List[Tuple[str, Usage, FrozenSet[str]]]


class _Names:
    """The variables a file names, to ask which of them concern a variable."""

    def __init__(self, named: _Named):
        self._exact: Dict[str, List[Tuple[Usage, FrozenSet[str]]]] = defaultdict(list)
        # every name and everything it is inside of: `a.b.c` is `a`, `a.b` and `a.b.c`
        self._inside: Dict[str, List[Usage]] = defaultdict(list)
        for name, usage, overridden in named:
            self._exact[name].append((usage, overridden))
            parts = name.split(".")
            for index in range(len(parts)):
                self._inside[".".join(parts[: index + 1])].append(usage)

    def concerning(self, variable: str) -> List[Usage]:
        """:return: the usages of names that are the variable, inside of it, or around it (`a.b` named uses all of `a`)"""
        parts = variable.split(".")
        usages = list(self._inside.get(variable, ()))
        for index in range(len(parts) - 1):
            # the variable is below the name: not used by what replaces it
            usages += [
                usage
                for usage, overridden in self._exact.get(".".join(parts[: index + 1]), ())
                if parts[index + 1] not in overridden
            ]
        return usages


class VariableUsages:
    """Which variables the plates use, and where. Computed once for all devices; make a new one after the files changed."""

    def __init__(self, config_dir: Path, devices: Iterable[DeviceFiles]):
        self._config_dir = config_dir
        self.definitions = VariableDefinitions(config_dir)
        # (variable file, leaf) -> where it is used, by any device
        self._usages: Dict[Tuple[Path, str], Set[Usage]] = defaultdict(set)
        # device folder -> variable file -> the leaves that device uses
        self._device_leaves: Dict[Path, Dict[Path, Set[str]]] = {}
        self._scans: Dict[Path, Dict[int, _Named]] = {}
        for device in devices:
            self._add_device(device)

    def usages(self, variable_file: Path, name: str) -> List[Usage]:
        """:return: where a variable of a file, and everything below it, is used, sorted"""
        variable_file = variable_file.resolve()
        inside = f"{name}."
        return sorted(
            {
                usage
                for (path, leaf), usages in self._usages.items()
                if path == variable_file and (leaf == name or leaf.startswith(inside))
                for usage in usages
            }
        )

    def used_names(self, device_path: Path) -> Dict[Path, List[str]]:
        """
        :return: the variable files whose variables a device uses -> the top-level names of these. A file that can't be read as
            YAML counts as used (with no names): better shown than hidden by mistake.
        """
        result: Dict[Path, List[str]] = {
            path: sorted({leaf.split(".")[0] for leaf in leaves})
            for path, leaves in self._device_leaves.get(device_path.resolve(), {}).items()
        }
        for variable_file in self.definitions.variable_files():
            if not self.definitions.is_readable(variable_file):
                result[variable_file.resolve()] = []
        return result

    def unused(self) -> Dict[Path, List[VariableLeaf]]:
        """:return: for each variable file (resolved path) the variables no device uses (not the ones the manager reads)"""
        result = {}
        for variable_file in self.definitions.variable_files():
            resolved = variable_file.resolve()
            leaves = [
                leaf
                for leaf in self.definitions.leaves(resolved)
                if leaf.name.split(".")[0] not in MANAGER_VARIABLES and not self._usages.get((resolved, leaf.name))
            ]
            if leaves:
                result[resolved] = leaves
        return result

    def _scan(self, file: Path) -> Dict[int, _Named]:
        """:return: the variables named in a file, by line"""
        if file not in self._scans:
            by_line: Dict[int, _Named] = {}
            for number, uses, types in scan_text(file.read_text(encoding="utf-8")):
                by_line[number] = [
                    (use.name, Usage(file, number, use.start, use.end - use.start), frozenset()) for use in uses
                ] + [(use.variable, Usage(file, number, use.start, use.end - use.start), use.keys) for use in types]
            self._scans[file] = by_line
        return self._scans[file]

    def _add_device(self, device: DeviceFiles):
        device_path = device.path.resolve()
        leaves_used = self._device_leaves.setdefault(device_path, {})
        files = [file.resolve() for file in device.files if file.is_file()]
        includers = self._includers(files)
        pending = [
            (context, [named for named_line in self._scan(file).values() for named in named_line])
            for file in files
            for context in _contexts(file, includers)
        ]
        while pending:
            context, named = pending.pop()
            names = _Names(named)
            for variable_file in self.definitions.candidates(context, device_path):
                variable_file = variable_file.resolve()
                for leaf in self.definitions.leaves(variable_file):
                    usages = names.concerning(leaf.name)
                    if not usages:
                        continue
                    self._usages[(variable_file, leaf.name)].update(usages)
                    if leaf.name not in leaves_used.setdefault(variable_file, set()):
                        leaves_used[variable_file].add(leaf.name)
                        # a variable that is used uses the variables its value names, as seen from the file that uses it
                        in_value = [
                            named
                            for number, named_line in self._scan(variable_file).items()
                            if leaf.line <= number <= leaf.last_line
                            for named in named_line
                        ]
                        if in_value:
                            pending.append((context, in_value))

    def _includers(self, files: List[Path]) -> Dict[Path, Set[Path]]:
        """:return: each part -> the files that include it (resolved paths)"""
        result: Dict[Path, Set[Path]] = defaultdict(set)
        for file in files:
            if file.suffix == ".jsonl":
                for path in included_paths(file.read_text(encoding="utf-8")):
                    result[Path(self._config_dir, path).resolve()].add(file)
        return result


def _contexts(file: Path, includers: Dict[Path, Set[Path]]) -> List[Path]:
    """:return: the file, and every file that includes it, also through other parts: the files whose variables it sees"""
    result = [file]
    for context in result:
        result += [including for including in sorted(includers.get(context, ())) if including not in result]
    return result
