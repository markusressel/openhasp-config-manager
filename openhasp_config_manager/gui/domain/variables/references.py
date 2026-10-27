"""
Where the templates of a text use variables: `{{ common.header.bar.height }}` uses the variable `common.header.bar.height`, and every
part of it can be Ctrl+clicked in the text editor. It looks at the text only (not at what is defined), and knows the objects whose
`obj` type has a theme (`theme.obj.<type>`), which a file uses without a template. Qt-free.
"""

import json
import re
from dataclasses import dataclass
from typing import FrozenSet, Iterator, List, Optional, Tuple

from openhasp_config_manager.gui.domain.source.syntax import find_templates

# the words of Jinja2 that look like variables
_KEYWORDS = frozenset(
    "if else elif endif for endfor in not and or is true false none True False None set endset macro endmacro call endcall "
    "block endblock extends include import from as with without context ignore missing raw endraw filter endfilter "
    "loop self caller varargs kwargs recursive scoped".split()
)
_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
# what `{% for a, b in %}` and `{% set a = %}` define: no variables of the config
_DEFINED = re.compile(r"(?<=\{%)(?:-?\s*for\s+)([\w\s,]+?)(?=\s+in\b)|(?<=\{%)(?:-?\s*set\s+)(\w+)(?=\s*=)")
_DELIMITER = re.compile(r"^\{[{%#]-?|-?[}%#]\}$")
_OBJECT_TYPE = re.compile(r'"obj"\s*:\s*"([^"{}]+)"')
_KEY = re.compile(r'"(\w+)"\s*:')


@dataclass(frozen=True)
class VariablePart:
    """A part of a variable in a template: `header` in `common.header.bar.height`, which stands for `common.header`."""

    start: int
    end: int
    # the variable up to and including this part
    name: str


@dataclass(frozen=True)
class VariableUse:
    """A variable in a template, e.g. `common.header.bar.height`, as its parts."""

    parts: Tuple[VariablePart, ...]

    @property
    def name(self) -> str:
        return self.parts[-1].name

    @property
    def start(self) -> int:
        return self.parts[0].start

    @property
    def end(self) -> int:
        return self.parts[-1].end


@dataclass(frozen=True)
class ObjectTypeUse:
    """The type of an object (`"obj": "btn"`), which gets the defaults of `theme.obj.btn` without a template."""

    start: int
    end: int
    type: str
    # the properties the object sets itself: they replace the ones of the theme
    keys: FrozenSet[str]

    @property
    def variable(self) -> str:
        return f"theme.obj.{self.type}"


def variable_uses(line: str) -> List[VariableUse]:
    """
    :return: the variables the templates of a line use. Filters, keywords and strings are no variables. A variable that is
        subscripted (`a.b[page]`) or has a method called on it (`a.b.items()`) can use all of `a.b`, and is `a.b`.
    """
    result = []
    for template in find_templates(line):
        text = line[template.start : template.end]
        if text.startswith("{#"):
            continue
        # strings can't hold variables: blank them (keeping the positions)
        text = _STRING.sub(lambda match: " " * len(match.group()), text)
        for defined in _DEFINED.finditer(text):
            group = 1 if defined.group(1) is not None else 2
            text = text[: defined.start(group)] + " " * len(defined.group(group)) + text[defined.end(group) :]
        delimiter = _DELIMITER.match(text)
        for match in _NAME.finditer(text, delimiter.end() if delimiter else 0):
            before = text[: match.start()].rstrip()
            # `| int` is a filter, and what follows a `.` is no variable of its own
            if before.endswith(("|", ".")):
                continue
            names = match.group().split(".")
            if text[match.end() :].lstrip().startswith("("):
                # `a.b.items(` is a method of `a.b`, `range(` a function
                names = names[:-1]
            if not names or names[0] in _KEYWORDS:
                continue
            parts = []
            position = template.start + match.start()
            for index, name in enumerate(names):
                parts.append(VariablePart(position, position + len(name), ".".join(names[: index + 1])))
                position += len(name) + 1
            result.append(VariableUse(tuple(parts)))
    return result


def part_at(line: str, column: int) -> Optional[VariablePart]:
    """:return: the part of a variable at a column of a line"""
    for use in variable_uses(line):
        for part in use.parts:
            if part.start <= column < part.end:
                return part
    return None


def _object_keys(line: str) -> FrozenSet[str]:
    """:return: the properties of the object of a line, also if the line is no valid JSON (e.g. a template outside of a string)"""
    try:
        parsed = json.loads(line)
    except ValueError:
        return frozenset(_KEY.findall(line))
    return frozenset(parsed) if isinstance(parsed, dict) else frozenset()


def object_type_uses(line: str) -> List[ObjectTypeUse]:
    matches = list(_OBJECT_TYPE.finditer(line))
    keys = _object_keys(line) if matches else frozenset()
    return [ObjectTypeUse(*match.span(1), match.group(1), keys) for match in matches]


def scan_text(text: str) -> Iterator[Tuple[int, List[VariableUse], List[ObjectTypeUse]]]:
    """:return: for every line of a text that has any (starting at 1): the variables its templates use, and its object types"""
    for number, line in enumerate(text.splitlines(), start=1):
        uses, types = variable_uses(line), object_type_uses(line)
        if uses or types:
            yield number, uses, types
