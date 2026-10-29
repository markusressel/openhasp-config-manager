"""
All Jinja2 handling of the config files lives here: rendering a template, resolving the templates of a dict that refer to
each other (`render_dict_recursive`), asking what a template needs or is missing, and where the templates of a text are. Everything else (deployment, GUI,
`check`) calls these functions instead of using Jinja2 directly, so they all agree on what a template means.

Templates in the config files are Jinja2 with some differences:

- **Unknown variables stay as they are written.** `{{ nope }}` renders to `{{ nope }}` (like `DebugUndefined`), because a
  variable may be defined by a later pass (see `render_dict_recursive`). `check_template` is the strict variant.
- **Templates nest.** `{{ p{{ page }}b1.x }}` renders the inner template first, then the outer one with its result. This is
  done by `render_template` and is not Jinja2 syntax.
- **Keys of dicts win over their methods.** `{{ cfg.values }}` is the variable `values` of `cfg`, not `dict.values`.
- **Templates are sandboxed.** They can't change what they are given or reach into Python internals, because configs may
  come from places the user doesn't control.
- **Values that are not sent as text have types.** The values of variables (`render_variables`) and of the `vars`/`for` of an
  `!include` are evaluated with `evaluate_template`: a single template is the value of its expression, other text with
  templates is text (a number if it is one). These are strict: an unknown name is an error.
"""

import copy
import logging
import re
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import jinja2
from jinja2 import BaseLoader, Template, TemplateError, TemplateSyntaxError, UndefinedError, meta, nodes
from jinja2.sandbox import ImmutableSandboxedEnvironment

from openhasp_config_manager.console import warn
from openhasp_config_manager.util import merge_dict_shared

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

# the names of the unknown variables that were written into the text a render produces, while one is collecting them
_UNKNOWN: ContextVar[Optional[Set[str]]] = ContextVar("unknown_template_variables", default=None)


class TemplateRenderError(ValueError):
    """A template of a dict can never be rendered, e.g. because it is not valid."""


class _Undefined(jinja2.Undefined):
    """An unknown variable renders as it is written, and is remembered."""

    __slots__ = ()

    def __str__(self) -> str:
        name = self._undefined_name or "?"
        unknown = _UNKNOWN.get()
        if unknown is not None:
            unknown.add(name)
        return f"{{{{ {name} }}}}"


class _Environment(ImmutableSandboxedEnvironment):
    def getattr(self, obj: Any, attribute: str) -> Any:
        # `cfg.values` is a variable named `values`, if there is one, not the method of the dict
        if isinstance(obj, dict) and attribute in obj:
            return obj[attribute]
        return super().getattr(obj, attribute)


_LENIENT = _Environment(loader=BaseLoader(), undefined=_Undefined)
_STRICT = _Environment(loader=BaseLoader(), undefined=jinja2.StrictUndefined)

_CACHE_SIZE = 4096


@lru_cache(maxsize=_CACHE_SIZE)
def _compile(content: str, strict: bool) -> Template:
    return (_STRICT if strict else _LENIENT).from_string(content)


def _find_nested_template(content: str) -> Optional[Tuple[int, int]]:
    """
    :return: the start and end of the first template that is inside of another one and has no template inside of it,
        e.g. `{{ page }}` in `{{ p{{ page }}b1.x }}`, or None. Quotes inside of templates are text.
    """
    open_at: List[int] = []
    quote: Optional[str] = None
    i = 0
    while i < len(content):
        char = content[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = None
        elif open_at and char in "'\"":
            quote = char
        elif content.startswith("{{", i):
            open_at.append(i)
            i += 1
        elif open_at and content.startswith("}}", i):
            start = open_at.pop()
            i += 1
            if open_at:
                return start, i + 1
        i += 1
    return None


def render_nested_templates(content: str, template_vars: Dict[str, Any], strict: bool = False) -> str:
    """
    Render only the templates that are inside of other templates (`{{ p{{ page }}b2.x }}` becomes `{{ p3b2.x }}`), which is
    the first step of `render_template`.
    """
    # a rendered template that is again inside of another one is not rendered again: at most one round for each "{{"
    for _ in range(content.count("{{")):
        nested = _find_nested_template(content)
        if nested is None:
            break
        start, end = nested
        content = content[:start] + _compile(content[start:end], strict).render(template_vars) + content[end:]
    return content


def render_template(content: str, template_vars: Dict[str, Any], strict: bool = False) -> str:
    """
    Render a text with templates. Templates inside of templates are rendered first.
    :param strict: raise for unknown variables instead of leaving them as they are written
    :raises jinja2.TemplateSyntaxError: for an invalid template
    :raises jinja2.UndefinedError: for an unknown variable, if `strict`
    """
    return _compile(render_nested_templates(content, template_vars, strict), strict).render(template_vars)


def render_template_collecting_unknown(content: str, template_vars: Dict[str, Any]) -> Tuple[str, Set[str]]:
    """
    Render a text, leaving unknown variables as they are written (see `render_template`).
    :return: the text, and the names of the unknown variables that are in it
    """
    rendered, unknown, error = _render_collecting(content, template_vars)
    if error is not None:
        raise error
    return rendered, unknown


def render_template_or_keep(content: str, template_vars: Dict[str, Any]) -> str:
    """
    Render a text, but keep it as written if an unknown variable can't be used the way the text uses it (`{{ p3b20.y + 5 }}`
    when `p3b20` doesn't exist, e.g. because its object got another id). Unknown variables that can simply be written back stay
    as they are, like in `render_template`.
    :raises jinja2.TemplateSyntaxError: for an invalid template
    """
    rendered, _, error = _render_collecting(content, template_vars)
    if error is None:
        return rendered
    if isinstance(error, UndefinedError):
        return content
    raise error


def _render_collecting(content: str, template_vars: Dict[str, Any]) -> Tuple[str, Set[str], Optional[Exception]]:
    """:return: the text (None if it failed), the unknown variables written into it so far, and why it failed"""
    unknown: Set[str] = set()
    token = _UNKNOWN.set(unknown)
    try:
        return render_template(content, template_vars), unknown, None
    except Exception as ex:
        return None, unknown, ex
    finally:
        _UNKNOWN.reset(token)


def check_template(content: str, template_vars: Dict[str, Any]) -> Optional[str]:
    """
    Check a template the way a deployment renders it, but report unknown variables, which a deployment leaves as they are.
    :return: why the template can't be rendered, or None if it can
    """
    try:
        render_template(content, template_vars, strict=True)
    except TemplateSyntaxError as ex:
        return f"Invalid template: {ex.message}"
    except UndefinedError as ex:
        return f"Unknown variable: {ex.message}"
    except TemplateError as ex:
        return f"Can't render: {ex.message}"
    return None


def template_syntax_error(content: str) -> Optional[str]:
    """
    Check only the syntax of the templates in a text, without variables (e.g. while it is typed). Templates inside of templates
    are checked on their own, and stand for a name in the template around them (`{{ p{{ page }}b1.x }}` is valid).
    :return: why the text can't be parsed, or None if it can
    """
    try:
        for _ in range(content.count("{{")):
            nested = _find_nested_template(content)
            if nested is None:
                break
            start, end = nested
            _compile(content[start:end], False)
            content = content[:start] + "_" + content[end:]
        _compile(content, False)
    except TemplateSyntaxError as ex:
        return f"Invalid template: {ex.message}"
    return None


def template_spans(text: str) -> List[Tuple[int, int]]:
    """
    :return: where the templates of a text are, as (start, end) with their delimiters, in order. A template inside of a
        template belongs to the outer one (`{{ p{{ page }}b1.x }}` is one). A template that is not closed reaches to the end.
    """
    result = []
    i = 0
    while i < len(text):
        if text.startswith("{{", i):
            end = _end_of_expression(text, i)
        elif text.startswith(("{%", "{#"), i):
            closing = "%}" if text[i + 1] == "%" else "#}"
            found = text.find(closing, i + 2)
            end = len(text) if found < 0 else found + 2
        else:
            i += 1
            continue
        result.append((i, end))
        i = end
    return result


def _end_of_expression(text: str, start: int) -> int:
    """:return: the index after the `}}` that closes the `{{` at `start` (counting nested ones), the end of the text if none"""
    depth = 0
    i = start
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


_OBJECT_NAME = re.compile(r"\bp\d+b\d+\b")


def has_nested_templates(content: str) -> bool:
    """:return: whether a template is inside of another one (`{{ p{{ page }}b2.x }}`)"""
    return _find_nested_template(content) is not None


def referenced_objects(content: str, template_vars: Dict[str, Any]) -> Optional[Set[str]]:
    """
    :param template_vars: the variables for the templates inside of templates, which are rendered first (see `render_template`)
    :return: the objects (`p1b2`) that the templates in a text name, also when a template builds the name
        (`{{ p{{ page }}b2.x }}` names `p3b2` if `page` is 3). None if that can't be told because a nested template is not valid.
    """
    if "{{" not in content and "{%" not in content:
        return set()
    try:
        return set(_OBJECT_NAME.findall(render_nested_templates(content, template_vars)))
    except TemplateError:
        return None


# what could not be rendered: where it is, and why
Unresolved = Tuple[str, str]


def render_dict_recursive(
    input: Dict,
    template_vars: Dict,
    result_key_path: List[str] = None,
) -> Dict[str, Any]:
    """
    Resolve the templates in the keys and values of a dict (and of the dicts and lists in it), which may refer to each
    other and to the `template_vars`. Entries that refer to something that is not defined yet are tried again after the
    others. Entries that never resolve are left out of the result, and reported.
    :param input: the dict which (possibly) contains templates
    :param template_vars: the variables the templates can use. Not changed.
    :param result_key_path: the keys of the dict within the variables, for the dicts inside of `input`
    :return: the dict with its templates rendered
    :raises TemplateRenderError: if a template is not valid
    """
    result, unresolved = _render_dict(input, copy.deepcopy(template_vars), result_key_path or [])
    if unresolved:
        warn("Can't render these templates: " + "; ".join(f"{name} ({reason})" for name, reason in unresolved))
    return result


def _render_dict(input: Dict, template_vars: Dict, path: List[str]) -> Tuple[Dict[str, Any], List[Unresolved]]:
    # `template_vars` is changed: every resolved entry is added to it at its place, for the templates that follow
    result = {}

    last_unresolved_names = None
    while True:
        unresolved: List[Unresolved] = []
        # the resolved part of the dicts that have entries left
        partial: Dict[str, Any] = {}
        for key, value in list(input.items()):
            name = ".".join(path + [key])
            rendered_key = key
            if "{{" in key:
                rendered_key, key_unresolved = _render_text(key, template_vars, name)
                if key_unresolved:
                    unresolved.append((name, f"the key {key_unresolved}"))
                    continue

            rendered_value, value_unresolved = _render_value(value, template_vars, path + [rendered_key], name)
            if value_unresolved:
                unresolved += value_unresolved
                if isinstance(value, dict):
                    partial[rendered_key] = rendered_value
                continue

            # later templates can use it
            target = template_vars
            for path_key in path:
                target = target.setdefault(path_key, {})
            target.pop(key, None)
            target[rendered_key] = rendered_value
            result[rendered_key] = rendered_value

        if not unresolved:
            return result, []
        unresolved_names = [name for name, _ in unresolved]
        if unresolved_names == last_unresolved_names:
            return {**result, **partial}, unresolved
        last_unresolved_names = unresolved_names


def _render_value(value: Any, template_vars: Dict, path: List[str], name: str) -> Tuple[Any, List[Unresolved]]:
    if isinstance(value, dict):
        return _render_dict(value, template_vars, path)
    if isinstance(value, str):
        rendered, reason = _render_text(value, template_vars, name)
        return rendered, [(name, reason)] if reason else []
    if isinstance(value, list):
        rendered_items = []
        reasons = []
        for item in value:
            if isinstance(item, str):
                item, reason = _render_text(item, template_vars, name)
                if reason:
                    reasons.append(reason)
            rendered_items.append(item)
        return rendered_items, [(name, "; ".join(reasons))] if reasons else []
    return value, []


def _render_text(text: str, template_vars: Dict, name: str) -> Tuple[str, Optional[str]]:
    """
    :return: the rendered text, and why it is not final (None if it is)
    :raises TemplateRenderError: if the template is not valid
    """
    rendered, unknown, error = _render_collecting(text, template_vars)
    if error is not None and not unknown:
        if isinstance(error, TemplateSyntaxError):
            raise TemplateRenderError(f"Invalid template in '{name}': {error.message}: {text}") from error
        # e.g. it uses the property of a variable that is not defined yet
        return text, f"can't be rendered: {error}"
    if unknown:
        # e.g. `{{ {{ a }} }}` is only valid when `a` is defined
        return rendered if error is None else text, "uses unknown " + ", ".join(sorted(unknown))
    return rendered, None


# --- values with types: the variables of the YAML files, the `vars` and `for` of an `!include` ---

_INTEGER = re.compile(r"-?\d+")
_FLOAT = re.compile(r"-?\d+\.\d+")
# stands for a template inside of a template while the names a template uses are collected
_NESTED = "__nested_template__"

# where a variable is: its keys (and the indices of lists), `common.margin` is ("common", "margin")
VariablePath = Tuple[Any, ...]


@lru_cache(maxsize=_CACHE_SIZE)
def _compile_expression(expression: str) -> Callable[..., Any]:
    return _STRICT.compile_expression(expression, undefined_to_none=False)


def is_single_template(text: str) -> bool:
    """:return: whether a text is one `{{ ... }}` and nothing else (spaces around it are fine)"""
    stripped = text.strip()
    return stripped.startswith("{{") and stripped.endswith("}}") and template_spans(stripped) == [(0, len(stripped))]


def evaluate_template(text: str, template_vars: Dict[str, Any]) -> Any:
    """
    The value of a text that is not sent to the plate as text, like a variable: a single template (`{{ common.margin * 2 }}`)
    is the value of its expression (a number, a list, a mapping, ...). Any other text is rendered (see `render_template`) and
    is a number if it is one (`"1{{ x }}"`). Unknown variables are errors.
    :raises jinja2.TemplateSyntaxError: for an invalid template
    :raises jinja2.UndefinedError: for an unknown variable
    """
    if not is_single_template(text):
        return _number(render_template(text, template_vars, strict=True))
    expression = render_nested_templates(text.strip(), template_vars, strict=True)[2:-2]
    value = _compile_expression(expression)(template_vars)
    if isinstance(value, jinja2.Undefined):
        # e.g. a key the mapping doesn't have: raises the UndefinedError
        str(value)
    return value


def _number(text: str) -> Any:
    if _INTEGER.fullmatch(text):
        return int(text)
    if _FLOAT.fullmatch(text):
        return float(text)
    return text


def render_variables(variables: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compute the variables of the YAML files whose values are templates (see `evaluate_template`), from each other: in the order
    they depend on each other, found from the names their templates use. Templates in keys are not rendered.
    :param variables: the variables, e.g. the merged variables of a path (they are not changed)
    :param context: more variables the templates can use, e.g. `device`. They win over `variables` (like a merge of both would)
        and are not rendered; variables they replace are not computed and stay as they are.
    :return: a copy of `variables` with the computed values
    :raises TemplateRenderError: for an invalid template, an unknown name, a cycle, or a template that can't be computed
    """
    context = context or {}
    result = copy.deepcopy(variables)
    leaves = {path: text for path, text in _template_leaves(result, ()) if not _overridden(context, path)}
    scope = merge_dict_shared(result, context)
    for path in leaves:
        # a template that uses a variable which is computed later fails (e.g. a name that a template inside of it builds)
        _set_at(scope, path, jinja2.StrictUndefined(hint=f"'{_dotted(path)}' is not computed yet"))
    for path in _dependency_order(leaves, scope):
        try:
            value = evaluate_template(leaves[path], scope)
        except Exception as ex:
            message = ex.message if isinstance(ex, TemplateError) else str(ex)
            raise TemplateRenderError(f"Can't compute the variable '{_dotted(path)}': {message}: {leaves[path]}") from ex
        _set_at(result, path, value)
        _set_at(scope, path, value)
    return result


def _template_leaves(value: Any, path: VariablePath) -> List[Tuple[VariablePath, str]]:
    if isinstance(value, dict):
        return [leaf for key, child in value.items() for leaf in _template_leaves(child, path + (key,))]
    if isinstance(value, list):
        return [leaf for index, child in enumerate(value) for leaf in _template_leaves(child, path + (index,))]
    if isinstance(value, str) and ("{{" in value or "{%" in value):
        return [(path, value)]
    return []


def _overridden(context: Dict[str, Any], path: VariablePath) -> bool:
    """:return: whether merging the context over the variables replaces the variable at the path"""
    current: Any = context
    for key in path:
        if not isinstance(current, dict):
            # a value of the context (e.g. a list) replaces everything below it
            return True
        if key not in current:
            return False
        current = current[key]
    return True


def _set_at(target: Any, path: VariablePath, value: Any):
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _dotted(path: VariablePath) -> str:
    return ".".join(str(key) for key in path)


def _dependency_order(leaves: Dict[VariablePath, str], scope: Dict[str, Any]) -> List[VariablePath]:
    """
    :return: the paths of the templates, each after the templates it uses
    :raises TemplateRenderError: for an unknown name or a cycle
    """
    dependencies = {path: _dependencies(path, text, leaves, scope) for path, text in leaves.items()}
    order: List[VariablePath] = []
    done: Set[VariablePath] = set()
    visiting: List[VariablePath] = []

    def visit(path: VariablePath):
        if path in done:
            return
        if path in visiting:
            cycle = visiting[visiting.index(path) :] + [path]
            raise TemplateRenderError("The variables depend on each other in a cycle: " + " -> ".join(map(_dotted, cycle)))
        visiting.append(path)
        for dependency in dependencies[path]:
            visit(dependency)
        visiting.pop()
        done.add(path)
        order.append(path)

    for path in leaves:
        visit(path)
    return order


def _dependencies(path: VariablePath, text: str, leaves: Dict[VariablePath, str], scope: Dict[str, Any]) -> List[VariablePath]:
    """:return: the templates the template at `path` uses: those at a name it uses, below it, or around it"""
    result = []
    for used in referenced_variables(text):
        unknown = _unknown_part(scope, used)
        if unknown is not None:
            raise TemplateRenderError(f"Unknown variable '{_dotted(unknown)}' in the variable '{_dotted(path)}': {text}")
        result += [leaf for leaf in leaves if leaf[: len(used)] == used or used[: len(leaf)] == leaf]
    return result


def _unknown_part(scope: Dict[str, Any], used: VariablePath) -> Optional[VariablePath]:
    """:return: the beginning of a name that is not a variable (`a.nope` of `a.nope.x`), None if the mappings have it"""
    current: Any = scope
    for index, key in enumerate(used):
        if not isinstance(current, dict):
            # e.g. `device`, a list or a value that is computed later: the rendering tells
            return None
        if key not in current:
            return used[: index + 1]
        current = current[key]
    return None


def referenced_variables(text: str) -> List[VariablePath]:
    """
    :return: the variables the templates of a text use, as far as they are written out: `{{ common.margin * 2 }}` uses
        ("common", "margin"), `{{ a[i] }}` uses ("a",) and ("i",). Names that a template inside of a template builds are not known.
        Names the templates define themselves (`{% for %}`, `{% set %}`) are left out.
    :raises TemplateRenderError: for an invalid template
    """
    parts = []
    outer = text
    for _ in range(text.count("{{")):
        nested = _find_nested_template(outer)
        if nested is None:
            break
        start, end = nested
        parts.append(outer[start:end])
        outer = outer[:start] + _NESTED + outer[end:]
    parts.append(outer)

    result: List[VariablePath] = []
    for part in parts:
        try:
            ast = _STRICT.parse(part)
            # the functions of Jinja2 (`range`, ...) are not in it
            free = meta.find_undeclared_variables(ast)
        except TemplateSyntaxError as ex:
            raise TemplateRenderError(f"Invalid template: {ex.message}: {text}") from ex
        _collect_paths(ast, free, result)
    return [path for path in result if _NESTED not in str(path[0])]


def _collect_paths(node: nodes.Node, free: Set[str], result: List[VariablePath]):
    if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Getattr):
        # a method (`a.keys()`) uses what it is called on
        _collect_paths(node.node.node, free, result)
        for child in node.iter_child_nodes():
            if child is not node.node:
                _collect_paths(child, free, result)
        return
    path = _reference_path(node)
    if path is not None and path[0] in free:
        result.append(path)
        return
    for child in node.iter_child_nodes():
        _collect_paths(child, free, result)


def _reference_path(node: nodes.Node) -> Optional[VariablePath]:
    """:return: the path of a name with its attributes and constant keys (`a.b["c"]`), None for anything else"""
    if isinstance(node, nodes.Name):
        return (node.name,)
    if isinstance(node, nodes.Getattr):
        base = _reference_path(node.node)
        return None if base is None else base + (node.attr,)
    if isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const):
        base = _reference_path(node.node)
        return None if base is None else base + (node.arg.value,)
    return None
