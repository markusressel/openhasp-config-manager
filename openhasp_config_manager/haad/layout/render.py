"""
Renders the owned objects of a page into openHASP JSONL objects (README §5.1), with the same processors and validator
that JSONL files go through, so code and JSONL files produce identical objects.
"""

from typing import Any, Dict, List

import orjson

from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor, ObjectThemeProcessor
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator

# openHASP cuts MQTT payloads off at its 2 kB buffer; keep a margin for the topic and the protocol
MAX_PAYLOAD_BYTES = 2048 - 128


def render_page(page, theme: Theme, config: Config, screen_width: int, screen_height: int) -> List[Dict[str, Any]]:
    """
    The JSONL objects of a page's owned objects, in declaration order, preceded by the page object (p<N>b0) with the
    theme's background (except for page 0, which lies over every page). Sets `jsonl` of every object. A page without
    owned objects renders to nothing.

    :param page: the PageController
    :param theme: default properties per object type
    :param config: the plate's configuration, for the JSONL processors
    :param screen_width: the screen size (after rotation), for percentages of objects without parent
    :param screen_height: see screen_width
    :raises ValueError: if the page mixes owned and external objects, or an object is invalid or too large for one payload
    """
    objects = list(page.objects.values())
    owned = [o for o in objects if o.owned]
    if not owned:
        return []
    external = [o for o in objects if not o.owned]
    if external:
        raise ValueError(
            f"Page {page.index} mixes owned objects (with a rect) and external objects (from the plate's flash: "
            + ", ".join(o.object_id for o in external)
            + "). Pushing the page clears it, which would delete the external objects."
        )

    theme_vars = {"theme": {"obj": {k: dict(v) for k, v in theme.obj.items()}}}
    result = [] if page.index == 0 else [{"page": page.index, "id": 0, "bg_color": theme.background_color, "bg_grad_dir": 0}]
    for obj in owned:
        if obj.parent is not None:
            width, height = obj.parent.jsonl["w"], obj.parent.jsonl["h"]
        else:
            width, height = screen_width, screen_height
        rect = obj.rect.resolve(width, height)
        data: Dict[str, Any] = {"page": page.index, "id": obj.obj_id, "obj": obj.obj_type}
        if obj.parent is not None:
            data["parentid"] = obj.parent.obj_id
        data.update({"x": rect.x, "y": rect.y, "w": rect.w, "h": rect.h})
        data.update(obj.static_props)
        data = ObjectThemeProcessor().process(data, config, theme_vars)
        data = ObjectDimensionsProcessor().process(data, config, theme_vars)
        obj.jsonl = data
        result.append(data)

    JsonlObjectValidator().validate("\n".join(orjson.dumps(o).decode("utf-8") for o in result))
    for line in result:
        size = len(orjson.dumps(line))
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"p{line['page']}b{line['id']} is {size} bytes as JSONL, more than fits into one payload ({MAX_PAYLOAD_BYTES})"
            )
    return result


def batch_lines(objects: List[Dict[str, Any]], max_bytes: int = MAX_PAYLOAD_BYTES) -> List[str]:
    """Packs JSONL objects into as few payloads as possible: whole lines, at most `max_bytes` per payload."""
    payloads: List[str] = []
    current: List[str] = []
    current_size = 0
    for obj in objects:
        line = orjson.dumps(obj).decode("utf-8")
        size = len(line.encode("utf-8"))
        # +1: the newline in front of the line
        if current and current_size + 1 + size > max_bytes:
            payloads.append("\n".join(current))
            current, current_size = [], 0
        current_size += size + (1 if current else 0)
        current.append(line)
    if current:
        payloads.append("\n".join(current))
    return payloads
