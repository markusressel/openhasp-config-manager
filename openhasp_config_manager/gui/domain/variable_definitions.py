"""
Where the variables are defined: the keys of the YAML files, and which files apply to which file (the rules of `VariableManager`).
This is what Ctrl+click on a variable of a template leads to: `{{ common.header.bar.height }}` leads to the `height:` of the YAML
file that defines it. Only the variables of YAML files are found (not those from `config.json`, the objects of the file, or the
Jinja2 language itself). Qt-free.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from openhasp_config_manager.const import COMMON_FOLDER_NAME


@dataclass(frozen=True)
class Definition:
    path: Path
    # starting at 1
    line: int
    column: int


@dataclass
class _Key:
    # starting at 1, and at 0: where the key is
    line: int
    column: int
    end_column: int
    # the last line of its value (inclusive)
    last_line: int
    children: Dict[str, "_Key"] = field(default_factory=dict)


@dataclass(frozen=True)
class VariableLeaf:
    """A variable of a YAML file that has no variables below it: its value is a text, a number, a list, ..."""

    # the dotted name, `common.header.bar.height`
    name: str
    # starting at 1, and at 0: where the key is
    line: int
    column: int
    # the last line of its value (inclusive): a template there is part of the variable
    last_line: int


def _keys_of(node: Optional[yaml.Node]) -> Dict[str, _Key]:
    if not isinstance(node, yaml.MappingNode):
        return {}
    result = {}
    for key_node, value_node in node.value:
        if isinstance(key_node, yaml.ScalarNode):
            end = value_node.end_mark
            # block collections and block scalars end where the next token starts, the other values right after their text
            block = end.column == 0 or (isinstance(value_node, yaml.CollectionNode) and not value_node.flow_style)
            result[key_node.value] = _Key(
                key_node.start_mark.line + 1,
                key_node.start_mark.column,
                key_node.end_mark.column,
                max(end.line if block else end.line + 1, key_node.start_mark.line + 1),
                _keys_of(value_node),
            )
    return result


class VariableDefinitions:
    """Finds the YAML file and line that define a variable for a file, following the rules of `VariableManager`."""

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir.resolve()
        # path -> ((modification time, size), keys), None for a file that is no valid YAML
        self._parsed: Dict[Path, Tuple[Tuple[int, int], Optional[Dict[str, _Key]]]] = {}

    def find(self, name: str, file: Path, device_path: Optional[Path] = None) -> Optional[Definition]:
        """
        :param name: the variable, e.g. `common.header.bar.height`
        :param file: the file whose template uses it
        :param device_path: the folder of the device that is edited: the files of the common folder also see its variables
        :return: where it is defined. Files in deeper folders override the ones above, and the folder of the device the files
            of the common folder. If only the start of the name is defined, that (so `a.b` of `a.b.c`).
        """
        file = file.resolve()
        for variable_file in self.candidates(file, None if device_path is None else device_path.resolve()):
            keys = self._keys(variable_file)
            found = None
            for depth, part in enumerate(name.split(".")):
                key = keys.get(part)
                if key is None:
                    break
                found = key
                keys = key.children
            else:
                return Definition(variable_file, found.line, found.column)
        return None

    def leaves(self, variable_file: Path) -> List[VariableLeaf]:
        """:return: the variables of a YAML file that have no variables below them, in the order of the file"""
        result: List[VariableLeaf] = []

        def visit(keys: Dict[str, _Key], prefix: str):
            for name, key in keys.items():
                full_name = prefix + name
                if key.children:
                    visit(key.children, full_name + ".")
                else:
                    result.append(VariableLeaf(full_name, key.line, key.column, key.last_line))

        visit(self._keys(variable_file.resolve()), "")
        return result

    def variable_files(self) -> List[Path]:
        """:return: all variable (YAML) files of the config directory, without those in hidden folders"""
        return sorted(
            path
            for path in self._config_dir.rglob("*.yaml")
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(self._config_dir).parts)
        )

    def candidates(self, file: Path, device_path: Optional[Path] = None) -> List[Path]:
        """:return: the variable files that apply to a file, the one that wins first"""
        file = file.resolve()
        chains = [self._folders(file.parent)]
        if device_path is not None and file.is_relative_to(self._config_dir / COMMON_FOLDER_NAME):
            chains.insert(0, self._folders(device_path))
        result = []
        for folders in chains:
            for folder in reversed(folders):
                # the files of a folder are merged in the order of their names, the last one wins
                result += sorted(folder.glob("*.yaml"), reverse=True)
        return [path for path in result if path.is_file()]

    def _folders(self, folder: Path) -> List[Path]:
        """:return: the config directory and the folders down to `folder`"""
        if not folder.is_relative_to(self._config_dir):
            return [self._config_dir]
        relative = folder.relative_to(self._config_dir)
        return [self._config_dir, *(self._config_dir.joinpath(*relative.parts[: i + 1]) for i in range(len(relative.parts)))]

    def is_readable(self, variable_file: Path) -> bool:
        """:return: whether a variable file is valid YAML (its variables are unknown otherwise)"""
        return self._read(variable_file.resolve()) is not None

    def _keys(self, path: Path) -> Dict[str, _Key]:
        return self._read(path) or {}

    def _read(self, path: Path) -> Optional[Dict[str, _Key]]:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._parsed.get(path)
        if cached is None or cached[0] != stamp:
            try:
                keys = _keys_of(yaml.compose(path.read_text(), Loader=yaml.SafeLoader))
            except (yaml.YAMLError, OSError, UnicodeDecodeError):
                keys = None
            cached = (stamp, keys)
            self._parsed[path] = cached
        return cached[1]


@dataclass(frozen=True)
class VariableKey:
    """A key of a variable file: the variable it defines, and where the key is in its line."""

    # the dotted name, `common.header.bar`
    name: str
    start: int
    end: int


def key_at(text: str, line: int, column: int) -> Optional[VariableKey]:
    """
    :param text: the text of a variable file (it may not be saved)
    :param line: starting at 1
    :param column: starting at 0
    :return: the key at that position, None if there is none or the text is no valid YAML
    """
    lines = text.splitlines()
    # cheap check first, this runs while the mouse moves: a key is left of the first colon
    if not 0 < line <= len(lines) or not 0 <= column < lines[line - 1].find(":"):
        return None
    try:
        keys = _keys_of(yaml.compose(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError:
        return None
    names: List[str] = []
    while True:
        for name, key in keys.items():
            if key.line == line and key.column <= column < key.end_column:
                return VariableKey(".".join([*names, name]), key.column, key.end_column)
            if key.line <= line <= key.last_line and key.children:
                names.append(name)
                keys = key.children
                break
        else:
            return None
