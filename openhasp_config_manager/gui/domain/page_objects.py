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
    SPINNER = "spinner"
    LED = "led"
    ROLLER = "roller"
    DROPDOWN = "dropdown"
    ARC = "arc"
    CHECKBOX = "checkbox"


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
    OpenHASPWidgetType.CHECKBOX: WidgetTypeInfo(
        title="Checkbox",
        description="Tick box with a text",
        icon="checkbox-marked-outline",
        defaults={"w": 150, "h": 30, "text": "Checkbox", "val": 0},
    ),
    OpenHASPWidgetType.ARC: WidgetTypeInfo(
        title="Arc",
        description="Round slider",
        icon="circle-slice-5",
        defaults={"w": 150, "h": 150, "min": 0, "max": 100, "val": 50},
    ),
    OpenHASPWidgetType.DROPDOWN: WidgetTypeInfo(
        title="Dropdown",
        description="Pick one of a list",
        icon="arrow-down-drop-circle-outline",
        defaults={"w": 150, "h": 30, "options": "Apple\nBanana\nOrange", "val": 0},
    ),
    OpenHASPWidgetType.ROLLER: WidgetTypeInfo(
        title="Roller",
        description="Scroll to pick an entry",
        icon="reload",
        defaults={"w": 150, "h": 100, "rows": 3, "options": "Apple\nBanana\nOrange", "val": 0},
    ),
    OpenHASPWidgetType.LED: WidgetTypeInfo(
        title="LED",
        description="Light with a brightness",
        icon="led-on",
        defaults={"w": 30, "h": 30, "val": 255},
    ),
    OpenHASPWidgetType.SPINNER: WidgetTypeInfo(
        title="Spinner",
        description="Busy indicator",
        icon="timer-sand",
        defaults={"w": 60, "h": 60, "angle": 60},
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
    :return: the objects of the page (hidden ones too), global objects last (they are drawn on top)
    """
    result = [
        obj
        for objects in component_objects.values()
        for obj in objects
        if obj.get("page") == index or (include_global and obj.get("page") == 0)
    ]

    # Draw objects on page 0 last (on top)
    result.sort(key=lambda obj: obj.get("page") == 0)
    return result


def is_hidden(obj: Dict) -> bool:
    """
    :return: whether the object is hidden on the plate (openHASP accepts true/false, 1/0 and their string forms)
    """
    return str(obj.get("hidden", False)).lower() in ("true", "1")


def step_page(pages: List[int], current: int, step: int) -> Optional[int]:
    """
    :param pages: the navigable page indices, sorted
    :param current: the current page index, which may not be one of them (e.g. an empty page)
    :param step: how many pages to go forward (negative: backward), rolling over at the ends
    :return: the page to go to, or None if there is none
    """
    if not pages:
        return None
    if current not in pages:
        return pages[0]
    return pages[(pages.index(current) + step) % len(pages)]


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
