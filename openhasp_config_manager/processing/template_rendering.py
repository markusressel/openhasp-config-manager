"""
All Jinja2 handling of the config files lives here: rendering a template, resolving the templates of a dict that refer to
each other (`render_dict_recursive`), and asking what a template needs or is missing. Everything else (deployment, GUI,
`check`) calls these functions instead of using Jinja2 directly, so they all agree on what a template means.

Templates in the config files are Jinja2 with some differences:

- **Unknown variables stay as they are written.** `{{ nope }}` renders to `{{ nope }}` (like `DebugUndefined`), because a
  variable may be defined by a later pass (see `render_dict_recursive`). `check_template` is the strict variant.
- **Templates nest.** `{{ p{{ page }}b1.x }}` renders the inner template first, then the outer one with its result. This is
  done by `render_template` and is not Jinja2 syntax.
- **Keys of dicts win over their methods.** `{{ cfg.values }}` is the variable `values` of `cfg`, not `dict.values`.
- **Templates are sandboxed.** They can't change what they are given or reach into Python internals, because configs may
  come from places the user doesn't control.
"""

import copy
import logging
import re
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

import jinja2
from jinja2 import BaseLoader, Template, TemplateError, TemplateSyntaxError, UndefinedError, meta
from jinja2.sandbox import ImmutableSandboxedEnvironment

from openhasp_config_manager.console import warn

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

# the innermost expressions of a text that can't be parsed as a whole, to parse them one by one
_EXPRESSION = re.compile(r"\{\{(?:(?!\{\{).)*?\}\}|\{%.*?%\}", re.DOTALL)

_CACHE_SIZE = 4096


@lru_cache(maxsize=_CACHE_SIZE)
def _compile(content: str, strict: bool) -> Template:
    return (_STRICT if strict else _LENIENT).from_string(content)


@lru_cache(maxsize=_CACHE_SIZE)
def _undeclared(text: str) -> frozenset:
    return frozenset(meta.find_undeclared_variables(_LENIENT.parse(text)))


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


def render_template(content: str, template_vars: Dict[str, Any], strict: bool = False) -> str:
    """
    Render a text with templates. Templates inside of templates are rendered first.
    :param strict: raise for unknown variables instead of leaving them as they are written
    :raises jinja2.TemplateSyntaxError: for an invalid template
    :raises jinja2.UndefinedError: for an unknown variable, if `strict`
    """
    # a rendered template that is again inside of another one is not rendered again: at most one round for each "{{"
    for _ in range(content.count("{{")):
        nested = _find_nested_template(content)
        if nested is None:
            break
        start, end = nested
        content = content[:start] + _compile(content[start:end], strict).render(template_vars) + content[end:]
    return _compile(content, strict).render(template_vars)


def render_template_collecting_unknown(content: str, template_vars: Dict[str, Any]) -> Tuple[str, Set[str]]:
    """
    Render a text, leaving unknown variables as they are written (see `render_template`).
    :return: the text, and the names of the unknown variables that are in it
    """
    rendered, unknown, error = _render_collecting(content, template_vars)
    if error is not None:
        raise error
    return rendered, unknown


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


def referenced_variables(text: str) -> Set[str]:
    """
    :return: the top-level names the templates in a text use, e.g. {"about"} for "{{ about.title }}". If the text can't be
        parsed as a whole (nested templates, a template that is not finished), the names of the innermost expressions that
        can. The names an outer template of nested templates uses are not known (`p{{ page }}b1` is not a name).
    """
    try:
        return set(_undeclared(text))
    except TemplateSyntaxError:
        result = set()
        for expression in _EXPRESSION.findall(text):
            try:
                result |= _undeclared(expression)
            except TemplateSyntaxError:
                continue
        return result


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
