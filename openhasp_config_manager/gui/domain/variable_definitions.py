"""
Where the variables of the templates are defined, for Ctrl+click in the text editor: `{{ common.header.bar.height }}` leads to the
`height:` in the YAML file that defines it. Only the variables of YAML files are found (not those from `config.json`, the objects
of the file, or the Jinja2 language itself). Qt-free.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from openhasp_config_manager.const import COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.source_syntax import find_templates

# the words of Jinja2 that look like variables
_KEYWORDS = frozenset(
    "if else elif endif for endfor in not and or is true false none True False None set endset macro endmacro call endcall "
    "block endblock extends include import from as with without context ignore missing raw endraw filter endfilter "
    "loop self caller varargs kwargs recursive scoped".split()
)
_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
_DELIMITER = re.compile(r"^\{[{%#]-?|-?[}%#]\}$")


@dataclass(frozen=True)
class VariableReference:
    """A part of a variable in a template: `header` in `common.header.bar.height`, which stands for `common.header`."""

    start: int
    end: int
    # the variable up to and including this part
    name: str


@dataclass(frozen=True)
class Definition:
    path: Path
    # starting at 1
    line: int
    column: int


def variable_references(line: str) -> List[VariableReference]:
    """:return: the parts of the variables in the templates of a line (not the filters, keywords, strings or methods)"""
    result = []
    for template in find_templates(line):
        text = line[template.start : template.end]
        if text.startswith("{#"):
            continue
        # strings can't hold variables: blank them (keeping the positions)
        text = _STRING.sub(lambda match: " " * len(match.group()), text)
        delimiter = _DELIMITER.match(text)
        body_start = delimiter.end() if delimiter else 0
        for match in _NAME.finditer(text, body_start):
            before = text[: match.start()].rstrip()
            after = text[match.end() :].lstrip()
            # `| int` is a filter, `.items()` a method, `a.b(` a call, `x=` the name of a keyword argument
            if before.endswith(("|", ".")) or after.startswith("("):
                continue
            parts = match.group().split(".")
            if parts[0] in _KEYWORDS:
                continue
            position = match.start()
            for index, part in enumerate(parts):
                start = template.start + position
                result.append(VariableReference(start, start + len(part), ".".join(parts[: index + 1])))
                position += len(part) + 1
    return result


def reference_at(line: str, column: int) -> Optional[VariableReference]:
    return next((ref for ref in variable_references(line) if ref.start <= column < ref.end), None)


@dataclass
class _Key:
    line: int
    column: int
    children: Dict[str, "_Key"] = field(default_factory=dict)


def _keys_of(node: Optional[yaml.Node]) -> Dict[str, _Key]:
    if not isinstance(node, yaml.MappingNode):
        return {}
    result = {}
    for key_node, value_node in node.value:
        if isinstance(key_node, yaml.ScalarNode):
            result[key_node.value] = _Key(key_node.start_mark.line + 1, key_node.start_mark.column, _keys_of(value_node))
    return result


class VariableDefinitions:
    """Finds the YAML file and line that define a variable for a file, following the rules of `VariableManager`."""

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir.resolve()
        # path -> ((modification time, size), keys)
        self._parsed: Dict[Path, Tuple[Tuple[int, int], Dict[str, _Key]]] = {}

    def find(self, name: str, file: Path, device_path: Optional[Path] = None) -> Optional[Definition]:
        """
        :param name: the variable, e.g. `common.header.bar.height`
        :param file: the file whose template uses it
        :param device_path: the folder of the device that is edited: the files of the common folder also see its variables
        :return: where it is defined. Files in deeper folders override the ones above, and the folder of the device the files
            of the common folder. If only the start of the name is defined, that (so `a.b` of `a.b.c`).
        """
        file = file.resolve()
        for variable_file in self._candidates(file, None if device_path is None else device_path.resolve()):
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

    def _candidates(self, file: Path, device_path: Optional[Path]) -> List[Path]:
        """:return: the variable files that apply to a file, the one that wins first"""
        chains = [self._folders(file.parent)]
        if device_path is not None and file.is_relative_to(self._config_dir / COMMON_FOLDER_NAME):
            chains.insert(0, self._folders(device_path))
        result = []
        for folders in chains:
            for folder in reversed(folders):
                # the files of a folder are merged in the order of their names, the last one wins
                result += sorted(folder.glob("*.yaml"), reverse=True)
                result += sorted(folder.glob("*.yml"), reverse=True)
        return [path for path in result if path.is_file()]

    def _folders(self, folder: Path) -> List[Path]:
        """:return: the config directory and the folders down to `folder`"""
        if not folder.is_relative_to(self._config_dir):
            return [self._config_dir]
        relative = folder.relative_to(self._config_dir)
        return [self._config_dir, *(self._config_dir.joinpath(*relative.parts[: i + 1]) for i in range(len(relative.parts)))]

    def _keys(self, path: Path) -> Dict[str, _Key]:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._parsed.get(path)
        if cached is None or cached[0] != stamp:
            try:
                keys = _keys_of(yaml.compose(path.read_text(), Loader=yaml.SafeLoader))
            except (yaml.YAMLError, OSError, UnicodeDecodeError):
                keys = {}
            cached = (stamp, keys)
            self._parsed[path] = cached
        return cached[1]
