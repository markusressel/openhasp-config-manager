import copy
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Dict, List, Optional

# openHASP object ids are 0..254 per page
MAX_OBJECT_ID = 254


class OpenHASPWidgetType(StrEnum):
    """The openHASP object types the editor can add, by their `obj` value."""

    LABEL = "label"
    BUTTON = "btn"
    SWITCH = "switch"
    IMAGE = "img"
    BAR = "bar"
    SLIDER = "slider"


@dataclass(frozen=True)
class WidgetTypeInfo:
    title: str
    description: str
    icon: str  # mdi6 icon name
    defaults: Dict


WIDGET_TYPES: Dict[OpenHASPWidgetType, WidgetTypeInfo] = {
    OpenHASPWidgetType.LABEL: WidgetTypeInfo(
        title="Label",
        description="Static or dynamic text",
        icon="format-text",
        defaults={"w": 120, "h": 40, "text": "Label", "align": "center"},
    ),
    OpenHASPWidgetType.BUTTON: WidgetTypeInfo(
        title="Button",
        description="Tap to run an action",
        icon="gesture-tap-button",
        defaults={"w": 120, "h": 50, "text": "Button", "radius": 8},
    ),
    OpenHASPWidgetType.SWITCH: WidgetTypeInfo(
        title="Switch",
        description="On/off toggle",
        icon="toggle-switch",
        defaults={"w": 80, "h": 40},
    ),
    OpenHASPWidgetType.IMAGE: WidgetTypeInfo(
        title="Image",
        description="Picture from the plate",
        icon="image",
        defaults={"w": 100, "h": 100, "src": ""},
    ),
    OpenHASPWidgetType.BAR: WidgetTypeInfo(
        title="Bar",
        description="Read-only progress",
        icon="poll",
        defaults={"w": 200, "h": 20, "min": 0, "max": 100, "val": 50},
    ),
    OpenHASPWidgetType.SLIDER: WidgetTypeInfo(
        title="Slider",
        description="Drag to set a value",
        icon="tune-variant",
        defaults={"w": 200, "h": 30, "min": 0, "max": 100, "val": 50},
    ),
}


def get_page_objects(
    component_objects: OrderedDict[str, List[Dict]],
    index: int,
    include_global: bool = True,
) -> List[Dict]:
    """
    Get the objects shown on the given page.
    :param component_objects: the objects of a draft, per jsonl component
    :param index: the index of the page
    :param include_global: whether to include global objects (page 0)
    :return: the objects of the page, global objects last (they are drawn on top)
    """
    result = [
        obj
        for objects in component_objects.values()
        for obj in objects
        if obj.get("page") == index or (include_global and obj.get("page") == 0)
    ]

    # Filter hidden objects
    result = [obj for obj in result if not obj.get("hidden", False)]

    # Draw objects on page 0 last (on top)
    result.sort(key=lambda obj: obj.get("page") == 0)
    return result


def get_navigable_page_indices(component_objects: OrderedDict[str, List[Dict]]) -> List[int]:
    """
    :return: the sorted indices of all pages that have objects, without the global page 0
    """
    used = {obj["page"] for objects in component_objects.values() for obj in objects if obj.get("page") is not None}
    return sorted(used - {0})


def count_objects(component_objects: OrderedDict[str, List[Dict]]) -> int:
    return sum(len(objects) for objects in component_objects.values())


def next_free_id(component_objects: OrderedDict[str, List[Dict]], page: int) -> int:
    """
    :return: the lowest object id that is not used on the given page
    """
    used = {obj.get("id") for objects in component_objects.values() for obj in objects if obj.get("page") == page}
    for candidate in range(1, MAX_OBJECT_ID + 1):
        if candidate not in used:
            return candidate
    raise ValueError(f"Page {page} has no free object id left")


def is_id_used(component_objects: OrderedDict[str, List[Dict]], page: int, obj_id: int, ignore: Dict) -> bool:
    """
    :param ignore: the object to leave out (the one the id is checked for)
    :return: whether another object on the given page already has the given id
    """
    return any(
        obj is not ignore and obj.get("page") == page and obj.get("id") == obj_id
        for objects in component_objects.values()
        for obj in objects
    )


def create_object(
    widget_type: OpenHASPWidgetType,
    page: int,
    obj_id: int,
    screen_width: int,
    screen_height: int,
) -> Dict:
    """
    Create a new object with sensible defaults, centered on the screen.
    """
    obj = {"page": page, "id": obj_id, "obj": str(widget_type), **copy.deepcopy(WIDGET_TYPES[widget_type].defaults)}
    obj["x"] = max(0, (screen_width - obj["w"]) // 2)
    obj["y"] = max(0, (screen_height - obj["h"]) // 2)
    return obj


def find_target_component(component_objects: OrderedDict[str, List[Dict]], page: int) -> Optional[str]:
    """
    Choose the jsonl component a new object of the given page goes into: the one with the most objects on that page,
    otherwise the last one.
    :return: the name of the component, or None if the draft has no components
    """
    if not component_objects:
        return None
    counts = {name: sum(1 for obj in objects if obj.get("page") == page) for name, objects in component_objects.items()}
    best = max(counts, key=lambda name: counts[name])
    if counts[best] > 0:
        return best
    return next(reversed(component_objects))


def add_object(component_objects: OrderedDict[str, List[Dict]], component_name: str, obj: Dict, after: Dict = None):
    """
    Add an object to a component of the draft, directly after `after` if given (keeps the z-order next to it).
    """
    objects = component_objects[component_name]
    if after is None:
        objects.append(obj)
        return
    position = next(i for i, other in enumerate(objects) if other is after)
    objects.insert(position + 1, obj)


def find_component_of(component_objects: OrderedDict[str, List[Dict]], obj: Dict) -> str:
    return next(name for name, objects in component_objects.items() if any(other is obj for other in objects))


def remove_object(component_objects: OrderedDict[str, List[Dict]], obj: Dict) -> bool:
    """
    Remove the given object (by identity, not equality) from whichever component of the draft holds it.
    :return: whether it was found
    """
    for objects in component_objects.values():
        for i, other in enumerate(objects):
            if other is obj:
                del objects[i]
                return True
    return False


def duplicate_object(component_objects: OrderedDict[str, List[Dict]], obj: Dict, offset: int = 10) -> Dict:
    """
    Duplicate an object into the same component, with the next free id on its page and moved by `offset`.
    :return: the new object
    """
    duplicate = copy.deepcopy(obj)
    duplicate["id"] = next_free_id(component_objects, obj.get("page", 0))
    duplicate["x"] = obj.get("x", 0) + offset
    duplicate["y"] = obj.get("y", 0) + offset
    add_object(component_objects, find_component_of(component_objects, obj), duplicate, after=obj)
    return duplicate
