"""
All Jinja2 handling of the config files lives here: rendering a template, resolving the templates of a dict that refer to
each other (`render_dict_recursive`), and asking what a template needs or is missing. Everything else (deployment, GUI,
`check`) calls these functions instead of using Jinja2 directly, so they all agree on what a template means.

Templates in the config files are Jinja2 with two additions:

- **Unknown variables stay as they are written.** `{{ nope }}` renders to `{{ nope }}` (`DebugUndefined`), because a variable
  may be defined by a later pass (see `render_dict_recursive`). `has_unresolved_variables` finds them in a result.
  `check_template` is the strict variant that reports them.
- **Templates nest.** `{{ p{{ page }}b1.x }}` renders the inner template first, then the outer one with its result. This is
  done by `render_template` and is not Jinja2 syntax.
"""

import copy
import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

import jinja2
from jinja2 import BaseLoader, Template, TemplateError, TemplateSyntaxError, UndefinedError, meta

from openhasp_config_manager.console import echo, error

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

# unknown variables render as they are written
_LENIENT = jinja2.Environment(loader=BaseLoader(), undefined=jinja2.DebugUndefined)
# unknown variables are errors
_STRICT = jinja2.Environment(loader=BaseLoader(), undefined=jinja2.StrictUndefined)

# a "{{ ... }}" inside of another template: the greedy match includes everything between the first "{{" and the last "}}"
_INNER_TEMPLATE = re.compile(r"\{\{.+}}")
# the innermost expressions of a text that can't be parsed as a whole, to parse them one by one
_EXPRESSION = re.compile(r"\{\{(?:(?!\{\{).)*?\}\}|\{%.*?%\}", re.DOTALL)

_CACHE_SIZE = 4096


@lru_cache(maxsize=_CACHE_SIZE)
def _compile(content: str, strict: bool) -> Template:
    return (_STRICT if strict else _LENIENT).from_string(content)


@lru_cache(maxsize=_CACHE_SIZE)
def _undeclared(text: str) -> frozenset:
    return frozenset(meta.find_undeclared_variables(_LENIENT.parse(text)))


def render_template(content: str, template_vars: Dict[str, Any], strict: bool = False) -> str:
    """
    Render a text with templates. Templates inside of templates are rendered first.
    :param strict: raise for unknown variables instead of leaving them as they are written
    :raises jinja2.TemplateSyntaxError: for an invalid template
    :raises jinja2.UndefinedError: for an unknown variable, if `strict`
    """
    # `content[2:-2]` is what is inside of the outer `{{ }}`, if the text is a single template
    inside = content[2:-2]
    for inner_template in _INNER_TEMPLATE.findall(inside):
        if inner_template != inside:
            content = content.replace(inner_template, render_template(inner_template, template_vars, strict))
    return _compile(content, strict).render(template_vars)


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


def has_unresolved_variables(rendered: Any) -> bool:
    """
    Whether a rendered value still refers to variables, because they were unknown (see `DebugUndefined`) or the text is
    an invalid template. Values that aren't text have none.
    """
    if not isinstance(rendered, str) or "{{" not in rendered:
        return False
    try:
        return bool(_undeclared(rendered))
    except TemplateSyntaxError:
        return True


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


def render_dict_recursive(
    input: Dict,
    template_vars: Dict,
    result_key_path: List[str] = None,
) -> Dict[str, Any]:
    """
    Resolve the templates in the keys and values of a dict (and of the dicts and lists in it), which may refer to each
    other and to the `template_vars`. Entries that refer to something that is not defined yet are tried again after the
    others; entries that never resolve are left out of the result.
    :param input: the dict which (possibly) contains templates
    :param template_vars: the variables the templates can use. Not changed.
    :param result_key_path: the keys of the dict within the variables, for the dicts inside of `input`
    :return: the dict with its templates rendered
    """
    return _render_dict(input, copy.deepcopy(template_vars), result_key_path or [])


def _render_dict(input: Dict, template_vars: Dict, result_key_path: List[str]) -> Dict[str, Any]:
    # `template_vars` is changed: every resolved entry is added to it at its place, for the templates that follow
    result = {}

    last_pending = None
    while True:
        pending = []
        for key, value in list(input.items()):
            rendered_key = key
            key_undefined = False
            if "{{" in key:
                try:
                    rendered_key = render_template(key, template_vars)
                    key_undefined = has_unresolved_variables(rendered_key)
                except Exception as ex:
                    error(f"Can't render the key '{key}': {ex}")
                    key_undefined = True

            value_undefined = False
            rendered_value = value
            if isinstance(value, dict) and not key_undefined:
                rendered_value = _render_dict(value, template_vars, result_key_path + [rendered_key])
            elif isinstance(value, list):
                try:
                    rendered_value = [render_template(item, template_vars) if isinstance(item, str) else item for item in value]
                    value_undefined = any(has_unresolved_variables(item) for item in rendered_value)
                except Exception:
                    value_undefined = True
            elif isinstance(value, str):
                try:
                    rendered_value = render_template(value, template_vars)
                    value_undefined = has_unresolved_variables(rendered_value)
                except Exception:
                    value_undefined = True

            if key_undefined:
                pending.append(key)
            if value_undefined:
                pending.append(f"{key}__value")

            if not (key_undefined or value_undefined):
                # later templates can use it
                tmp = template_vars
                for path_key in result_key_path:
                    tmp = tmp.setdefault(path_key, {})
                tmp.pop(key, None)
                tmp[rendered_key] = rendered_value
                result[rendered_key] = rendered_value

        if not pending:
            return result
        if pending == last_pending:
            echo(f"No progression while rendering templates, unable to render: {pending}")
            return result
        last_pending = pending
