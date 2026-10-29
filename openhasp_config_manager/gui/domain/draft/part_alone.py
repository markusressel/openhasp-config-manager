"""A part shown on its own, without a file that includes it: the variables it needs from an `!include`."""

import re
from typing import Any, Dict, Iterator, List

from openhasp_config_manager.processing.jsonl.includes import FOR, INCLUDE, is_directive
from openhasp_config_manager.processing.template_rendering import THIS, TemplateRenderError, referenced_variables

# the value of a variable the part needs, until the user enters one: a page, an id and a number
PLACEHOLDER = 1
# names that are no variables of an `!include`: the objects (`p1b2`, `b2`) and the object itself
_OBJECT_NAME = re.compile(rf"p\d+b\d+|b\d+|{THIS}")


def placeholder_vars(sources: List[Dict[str, Any]], variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    :param sources: the objects of a part, as written in it
    :param variables: the variables the part has without an `!include` (of its folders and the device)
    :return: the `vars` an `!include` of the part needs: every variable its templates use that `variables` doesn't have,
        `PLACEHOLDER` each (`tile.caption` is the mapping `{"tile": {"caption": 1}}`, which an `!include` merges into the
        `tile` of the folder's defaults)
    """
    result: Dict[str, Any] = {}
    for source in sources:
        # the `vars` of an `!include` in the part see the variables of its `for`
        local = set(source.get(FOR, {})) if is_directive(source) else set()
        for text in _texts(source):
            try:
                paths = referenced_variables(text)
            except TemplateRenderError:
                # the part reports it when it is rendered
                continue
            for path in paths:
                if path[0] in local or _OBJECT_NAME.fullmatch(str(path[0])) or not _is_missing(variables, path):
                    continue
                _set_placeholder(result, [str(key) for key in path])
    return result


def _is_missing(variables: Dict[str, Any], path: tuple) -> bool:
    """:return: whether the mappings of the variables don't have the path (a value that is no mapping may have anything)"""
    current: Any = variables
    for key in path:
        if not isinstance(current, dict):
            return False
        if key not in current:
            return True
        current = current[key]
    return False


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key != INCLUDE:
                yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def _set_placeholder(target: Dict[str, Any], path: List[str]):
    """Set a placeholder at a path, unless it has a value there already. A mapping wins over a placeholder."""
    for key in path[:-1]:
        if not isinstance(target.get(key), dict):
            target[key] = {}
        target = target[key]
    target.setdefault(path[-1], PLACEHOLDER)
