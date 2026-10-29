"""
Directives in .jsonl files: JSON objects whose key starts with `!`, which openhasp-config-manager replaces before anything is sent
to a plate. An object is either an openHASP object or a directive. The only directive is `!include`, which replaces itself with
the objects of another .jsonl file (a "part"), with variables of its own and optionally once per combination of loop values:

    {"!include": "common/parts/tile.jsonl", "vars": {"id": 29, "caption": "Elapsed"}, "for": {"column": [0, 1]}}

See `docs/include-directive.md` for the design: the variables of a part (`instance_scope`), ids, errors and where the objects
come from (`ObjectOrigin`).
"""

import itertools
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Set, Tuple

from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor
from openhasp_config_manager.processing.template_rendering import (
    THIS,
    TemplateRenderError,
    evaluate_template,
    is_single_template,
    referenced_variables,
    render_template_or_keep,
    render_variables,
)
from openhasp_config_manager.util import merge_dict_shared

DIRECTIVE_PREFIX = "!"
INCLUDE = "!include"
VARS = "vars"
FOR = "for"
# the keys an `!include` can have besides the path
INCLUDE_KEYS = (VARS, FOR)
# more instances of one `!include` are a mistake (openHASP has 12 pages with ids up to 254)
MAX_INSTANCES = 1000
# the names of objects in templates: `p1b2`, `b2` (see `object_variables`)
_OBJECT_NAME = re.compile(r"(p\d+)?b\d+")


def is_directive(source: Dict[str, Any]) -> bool:
    """:return: whether a source object is a directive (it has a key that starts with `!`), not an openHASP object"""
    return any(isinstance(key, str) and key.startswith(DIRECTIVE_PREFIX) for key in source)


def include_path(source: Dict[str, Any]) -> Optional[str]:
    """:return: the path an `!include` names as it is written, None if the object is no `!include` or the path is no text"""
    path = source.get(INCLUDE)
    return path if isinstance(path, str) else None


def directive_error(source: Dict[str, Any]) -> Optional[str]:
    """
    Check a directive object without the config: its keys, the form of its path, `vars` and `for`.
    :return: what is wrong with it, None if nothing (or if it is no directive)
    """
    if not is_directive(source):
        return None
    unknown = [key for key in source if key.startswith(DIRECTIVE_PREFIX) and key != INCLUDE]
    if unknown:
        return f"Unknown directive {', '.join(unknown)}: the only directive is {INCLUDE}"
    extra = [key for key in source if key != INCLUDE and key not in INCLUDE_KEYS]
    if extra:
        return (
            f"An {INCLUDE} has only '{VARS}' and '{FOR}' next to its path, not {', '.join(extra)} "
            f"(an object is either an openHASP object or a directive)"
        )
    path = source[INCLUDE]
    if not isinstance(path, str) or not path.strip():
        return f'The path of an {INCLUDE} must be a text, e.g. "common/parts/tile.jsonl"'
    if "{{" in path or "{%" in path:
        return f"The path of an {INCLUDE} can't be a template, it is written as it is: {path}"
    if not path.endswith(".jsonl"):
        return f"An {INCLUDE} includes a .jsonl file, not: {path}"
    for key in INCLUDE_KEYS:
        if key in source and not isinstance(source[key], dict):
            return f"'{key}' of an {INCLUDE} must be an object of names and values"
    loops = source.get(FOR, {})
    for name, values in loops.items():
        if not name.isidentifier():
            return f"'{name}' of '{FOR}' is not a name that templates can use"
        if not isinstance(values, list) and not (isinstance(values, str) and is_single_template(values)):
            return f"'{FOR}' of '{name}' must be a list or a single template, e.g. \"{{{{ range(1, 6) }}}}\""
    both = sorted(set(loops) & set(source.get(VARS, {})))
    if both:
        return f"{', '.join(both)} is in '{VARS}' and in '{FOR}': use one of them"
    return None


@dataclass(frozen=True)
class IncludeStep:
    """One `!include` on the way to an included object."""

    # the file with the directive
    file: Path
    # the index of the directive in the objects of that file
    index: int
    # starting at 1
    line: int
    # the `vars` of the directive, rendered
    vars: Dict[str, Any] = field(default_factory=dict, compare=False)
    # the values of the `for` variables of this instance
    loop: Dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class ObjectOrigin:
    """Where an object is written: its file, and the `!include`s that put it into the file being processed."""

    file: Path
    # the index of the object in the objects of its file
    index: int
    # starting at 1, None for an object that is not in a file (e.g. added in the editor)
    line: Optional[int]
    # outermost first, empty for an object of the file itself
    includes: Tuple[IncludeStep, ...] = ()

    @property
    def is_included(self) -> bool:
        return bool(self.includes)


@dataclass
class ExpandedObject:
    """An object of a .jsonl file after the directives are replaced."""

    # the object as written in its file, with its templates
    source: Dict[str, Any]
    origin: ObjectOrigin
    # the variables of the instance of a part the object belongs to (see `instance_scope`), empty for an object of the file
    scope: Dict[str, Any] = field(default_factory=dict)
    # the name of an included object (`p3b29`), whose page and id are rendered when it is included; None for the other objects
    name: Optional[str] = None


@dataclass(frozen=True)
class IncludeError:
    """What is wrong with a directive, or with an object it includes."""

    message: str
    # where: the directive, or the object of a part
    file: Path
    line: int
    # the `!include`s that lead to the file, outermost first; empty if it is the file being processed
    includes: Tuple[IncludeStep, ...] = ()

    def describe(self, config_dir: Path) -> str:
        """:return: the error with its place and the includes that lead to it, e.g. for an exception"""
        text = f"{display_path(self.file, config_dir)}:{self.line}: {self.message}"
        return text + (f" ({describe_includes(self.includes, config_dir)})" if self.includes else "")


@dataclass
class Expansion:
    """The objects of a file after its directives are replaced, in their order, and what went wrong."""

    objects: List[ExpandedObject]
    errors: List[IncludeError]


@dataclass(frozen=True)
class PartFile:
    path: Path
    content: str
    # the objects of the file as written (see `DeviceProcessor.parse_jsonl_objects`)
    sources: List[Dict[str, Any]]


class IncludeLookupError(Exception):
    """A part can't be included, e.g. because the file doesn't exist."""


class IncludeExpansionError(ValueError):
    """The directives of a file can't be expanded."""

    def __init__(self, errors: List[IncludeError], config_dir: Path):
        super().__init__("; ".join(error.describe(config_dir) for error in errors))
        self.errors = errors


class IncludedObjectError(ValueError):
    """An object of a part can't be rendered (`__cause__` says why)."""

    def __init__(self, origin: ObjectOrigin, config_dir: Path, reason: str):
        where = f"{display_path(origin.file, config_dir)}:{origin.line}"
        super().__init__(f"{where}: {reason} ({describe_includes(origin.includes, config_dir)})")
        self.origin = origin
        self.reason = reason


class PartResolver(Protocol):
    """What the expansion needs from the config: the files that can be included, and their default variables."""

    config_dir: Path

    def part(self, path: str) -> PartFile:
        """
        :param path: the path of an `!include`, relative to the config directory
        :raises IncludeLookupError: if it is no file that can be included
        """
        ...

    def defaults(self, path: Path) -> Dict[str, Any]:
        """:return: the variables of the YAML files of the folders of a part, not computed (see `VariableManager.get_raw_vars`)"""
        ...


def display_path(path: Path, config_dir: Path) -> str:
    """:return: the path relative to the config directory, as in the `!include`s"""
    try:
        return Path(path).resolve().relative_to(Path(config_dir).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def describe_step(step: IncludeStep, config_dir: Path) -> str:
    """:return: where the directive is, and the loop values of the instance, e.g. `common/page/pr/content.jsonl:12 (column=1)`"""
    loop = ", ".join(f"{name}={value!r}" for name, value in step.loop.items())
    return f"{display_path(step.file, config_dir)}:{step.line}" + (f" ({loop})" if loop else "")


def describe_includes(includes: Iterable[IncludeStep], config_dir: Path) -> str:
    """:return: e.g. "included at common/page/pr/content.jsonl:12 (column=1) > common/parts/tile.jsonl:3", outermost first"""
    return "included at " + " > ".join(describe_step(step, config_dir) for step in includes)


@lru_cache(maxsize=64)
def _source_editor(content: str) -> JsonlSourceEditor:
    return JsonlSourceEditor(content)


def _line_of(content: str, index: int) -> int:
    return _source_editor(content).line_of(index)


def instance_scope(
    defaults: Dict[str, Any], scope: Dict[str, Any], variables: Dict[str, Any], loop: Dict[str, Any]
) -> Dict[str, Any]:
    """
    The variables of an instance of a part. Merged deeply, later ones win:
    1. `defaults`: the variables of the YAML files of the folders of the part,
    2. `scope`: everything the including file sees at the directive,
    3. `variables`: the `vars` of the directive,
    4. `loop`: the values of the `for` variables of the instance.
    The templates of the defaults that are not replaced are then computed with all of it (see `render_variables`).
    The result shares its values with the arguments: don't change it.
    :raises TemplateRenderError: if a default can't be computed
    :raises AssertionError: if a value replaces a mapping
    """
    context = merge_dict_shared(merge_dict_shared(scope, variables), loop)
    return merge_dict_shared(render_variables(defaults, context), context)


class _Expander:
    def __init__(self, resolver: PartResolver):
        self._resolver = resolver
        self.objects: List[ExpandedObject] = []
        self.errors: List[IncludeError] = []

    def expand(
        self,
        file: Path,
        content: str,
        sources: List[Dict[str, Any]],
        scope: Dict[str, Any],
        includes: Tuple[IncludeStep, ...],
        visiting: Set[Path],
    ):
        for index, source in enumerate(sources):
            if is_directive(source):
                self._include(file, content, index, source, scope, includes, visiting)
            elif includes:
                self._add_included(file, content, index, source, scope, includes)
            else:
                # its line is the session's business: the objects of a draft are not where they are in the file
                self.objects.append(ExpandedObject(source, ObjectOrigin(file, index, None)))

    def _error(self, message: str, file: Path, line: int, includes: Tuple[IncludeStep, ...]):
        self.errors.append(IncludeError(message, file, line, includes))

    def _add_included(self, file: Path, content: str, index: int, source: Dict[str, Any], scope: Dict[str, Any], includes):
        line = _line_of(content, index)
        try:
            page, object_id = (_number(evaluate_template(str(source.get(key, 0)), scope)) for key in ("page", "id"))
        except Exception as ex:
            self._error(f"Can't render the page and id of the object: {_reason(ex)}", file, line, includes)
            return
        if not isinstance(page, int) or not isinstance(object_id, int):
            self._error(
                f"The page and id of an included object must be numbers, not {page!r} and {object_id!r}", file, line, includes
            )
            return
        origin = ObjectOrigin(file, index, line, includes)
        self.objects.append(ExpandedObject(source, origin, scope, f"p{page}b{object_id}"))

    def _include(
        self,
        file: Path,
        content: str,
        index: int,
        source: Dict[str, Any],
        scope: Dict[str, Any],
        includes: Tuple[IncludeStep, ...],
        visiting: Set[Path],
    ):
        line = _line_of(content, index)
        error = directive_error(source)
        if error is not None:
            self._error(error, file, line, includes)
            return
        try:
            part = self._resolver.part(source[INCLUDE])
        except IncludeLookupError as ex:
            self._error(str(ex), file, line, includes)
            return
        config_dir = self._resolver.config_dir
        if Path(part.path).resolve() in visiting:
            chain = [f"{display_path(step.file, config_dir)}:{step.line}" for step in includes]
            chain += [f"{display_path(file, config_dir)}:{line}", display_path(part.path, config_dir)]
            self._error(f"The {INCLUDE}s include each other in a cycle: {' -> '.join(chain)}", file, line, includes)
            return
        try:
            combinations = self._combinations(source.get(FOR, {}), scope)
        except _DirectiveError as ex:
            self._error(str(ex), file, line, includes)
            return
        defaults = self._resolver.defaults(Path(part.path))
        for loop in combinations:
            try:
                variables = {name: _evaluate(value, {**scope, **loop}, name) for name, value in source.get(VARS, {}).items()}
                part_scope = instance_scope(defaults, scope, variables, loop)
            except (_DirectiveError, TemplateRenderError, AssertionError) as ex:
                self._error(str(ex), file, line, includes)
                return
            step = IncludeStep(file, index, line, variables, loop)
            self.expand(
                part.path, part.content, part.sources, part_scope, includes + (step,), visiting | {Path(part.path).resolve()}
            )

    @staticmethod
    def _combinations(loops: Dict[str, Any], scope: Dict[str, Any]) -> List[Dict[str, Any]]:
        values = []
        for name, value in loops.items():
            evaluated = _evaluate(value, scope, f"{FOR}.{name}")
            if isinstance(evaluated, (str, bytes, dict)) or not _iterable(evaluated):
                raise _DirectiveError(f"'{FOR}' of '{name}' is not a list of values: {evaluated!r}")
            if hasattr(evaluated, "__len__") and len(evaluated) > MAX_INSTANCES:
                raise _DirectiveError(f"'{FOR}' of '{name}' has {len(evaluated)} values, more than {MAX_INSTANCES}")
            values.append(list(evaluated))
        count = 1
        for items in values:
            count *= len(items)
        if count > MAX_INSTANCES:
            raise _DirectiveError(f"'{FOR}' makes {count} instances, more than {MAX_INSTANCES}")
        names = list(loops)
        return [dict(zip(names, combination)) for combination in itertools.product(*values)]


class _DirectiveError(Exception):
    pass


def _iterable(value: Any) -> bool:
    try:
        iter(value)
    except TypeError:
        return False
    return True


def _number(value: Any) -> Any:
    """:return: a number for an integral float (`{{ id / 1 }}`), other values as they are"""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _reason(ex: Exception) -> str:
    return str(getattr(ex, "message", None) or ex)


def _evaluate(value: Any, scope: Dict[str, Any], name: str) -> Any:
    """:return: a value of `vars` or `for` with its templates evaluated (see `evaluate_template`), also inside lists and mappings"""
    if isinstance(value, dict):
        return {key: _evaluate(item, scope, f"{name}.{key}") for key, item in value.items()}
    if isinstance(value, list):
        return [_evaluate(item, scope, name) for item in value]
    if not isinstance(value, str) or ("{{" not in value and "{%" not in value):
        return value
    try:
        return evaluate_template(value, scope)
    except Exception as ex:
        objects = [path[0] for path in _safe_references(value) if path[0] not in scope and _names_object(str(path[0]))]
        if objects:
            raise _DirectiveError(
                f"'{name}' refers to the object {objects[0]}, but the variables of an {INCLUDE} are rendered before the "
                f"objects. Pass its id and refer to it in the part instead, e.g. {{{{ b{{{{ anchor }}}}.x }}}}: {value}"
            ) from ex
        raise _DirectiveError(f"Can't render '{name}': {_reason(ex)}: {value}") from ex


def _safe_references(value: str) -> List[Tuple[Any, ...]]:
    try:
        return referenced_variables(value)
    except TemplateRenderError:
        return []


def _names_object(name: str) -> bool:
    """:return: whether a name is one of an object: `p1b2`, `b2` or `this`"""
    return name == THIS or _OBJECT_NAME.fullmatch(name) is not None


def _check_names(expansion: Expansion, scope: Dict[str, Any], config_dir: Path):
    """Add an error for every included object whose page and id another object of the file has as well."""
    named: Dict[str, List[ExpandedObject]] = {}
    for obj in expansion.objects:
        name = obj.name or _plain_name(obj.source, scope)
        if name is not None:
            named.setdefault(name, []).append(obj)
    for name, objects in named.items():
        if len(objects) < 2 or not any(obj.origin.is_included for obj in objects):
            continue
        # every included object that has the name of an object before it, or the first one if only that one is included
        colliding = [obj for obj in objects[1:] if obj.origin.is_included] or objects[:1]
        for obj in colliding:
            others = ", ".join(_describe_origin(other.origin, config_dir) for other in objects if other is not obj)
            step = obj.origin.includes[-1]
            message = f"{name} of {_describe_origin(obj.origin, config_dir)} is also the id of {others}"
            expansion.errors.append(IncludeError(message, step.file, step.line, obj.origin.includes[:-1]))


def _describe_origin(origin: ObjectOrigin, config_dir: Path) -> str:
    where = display_path(origin.file, config_dir) + (f":{origin.line}" if origin.line is not None else "")
    loops = ", ".join(f"{name}={value!r}" for step in origin.includes for name, value in step.loop.items())
    return where + (f" ({loops})" if loops else "")


def _plain_name(source: Dict[str, Any], scope: Dict[str, Any]) -> Optional[str]:
    """:return: the name of an object of the file itself, as far as it can be rendered with the variables (None if not)"""
    parts = []
    for key in ("page", "id"):
        value = source.get(key, 0)
        text = render_template_or_keep(value, scope) if isinstance(value, str) else str(value)
        if "{" in text:
            return None
        parts.append(text)
    return f"p{parts[0]}b{parts[1]}"


def expand_includes(
    file: Path, content: str, sources: List[Dict[str, Any]], scope: Dict[str, Any], resolver: PartResolver
) -> Expansion:
    """
    Replace the directives of a file with the objects they include, recursively.
    :param file: the file, `content` its text (for the lines of the directives), `sources` its objects as written
    :param scope: the variables the objects of the file are rendered with (without the objects)
    :return: the objects in their order, and what went wrong (a directive with an error includes nothing)
    """
    expander = _Expander(resolver)
    expander.expand(Path(file), content, sources, scope, (), {Path(file).resolve()})
    expansion = Expansion(expander.objects, expander.errors)
    _check_names(expansion, scope, resolver.config_dir)
    return expansion


def directive_paths(sources: Iterable[Dict[str, Any]]) -> List[str]:
    """:return: the paths the `!include`s of the objects of a file name, as written"""
    return [path for source in sources if is_directive(source) and (path := include_path(source)) is not None]
