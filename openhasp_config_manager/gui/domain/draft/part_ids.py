"""The page and id of an object that is added to a part: templates, so that each instance of the part gets its own object."""

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# an id template of a part: `{{ id }}`, `{{ id + 2 }}`, `{{ ids.base + 12 }}`
_ID_TEMPLATE = re.compile(r"\{\{\s*(?P<base>[A-Za-z_][\w.]*)\s*(?:\+\s*(?P<offset>\d+)\s*)?\}\}")


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and "{{" in value


def new_part_object_ids(part_sources: List[Dict[str, Any]], source: Dict[str, Any]) -> Tuple[Any, Any]:
    """
    :param part_sources: the objects of the part (without its directives)
    :param source: the new object, with a page and id of the page it is added to
    :return: its page and id in the part. The page is the template most objects of the part use (or the page of `source`, if
        it is a template already, or no object of the part has one). The id is the next one after the ids of the part if they
        are all a variable plus a number (`{{ id }}`, `{{ id + 1 }}`), otherwise the id of `source`: every instance then gets
        that id, which the editor reports as a collision.
    """
    page = source.get("page")
    pages = Counter(obj["page"] for obj in part_sources if _is_template(obj.get("page")))
    if not _is_template(page) and pages:
        page = pages.most_common(1)[0][0]
    return page, _next_id(part_sources) or source.get("id")


def _next_id(part_sources: List[Dict[str, Any]]) -> Optional[str]:
    """:return: the id template after those of the part, None if there is no obvious one"""
    matches = [_ID_TEMPLATE.fullmatch(str(obj.get("id", "")).strip()) for obj in part_sources]
    if not matches or None in matches or len({match["base"] for match in matches}) != 1:
        return None
    offset = max(int(match["offset"] or 0) for match in matches) + 1
    return f"{{{{ {matches[0]['base']} + {offset} }}}}"
