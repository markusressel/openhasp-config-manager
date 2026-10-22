from typing import Callable, Dict, List, Tuple

READ_ONLY_PROPERTIES = {"page", "obj"}
PIXEL_PROPERTIES = {
    "x",
    "y",
    "w",
    "h",
    "radius",
    "border_width",
    "outline_width",
    "pad_top",
    "pad_bottom",
    "pad_left",
    "pad_right",
    "pad_inner",
}

# (group title, predicate on the property name), the first matching group wins
_GROUPS: List[Tuple[str, Callable[[str], bool]]] = [
    ("Object", lambda key: key in {"page", "id", "obj", "parentid", "groupid"}),
    ("Position", lambda key: key in {"x", "y"}),
    ("Size", lambda key: key in {"w", "h"}),
    ("Text", lambda key: key in {"text", "align", "mode"} or key.startswith(("text_", "value_"))),
    (
        "Style",
        lambda key: (
            "color" in key
            or key.startswith(("bg_", "border_", "outline_", "shadow_", "pad_", "line_", "radius", "opa", "image_", "scale_"))
            or key in {"radius", "src", "zoom", "angle"}
        ),
    ),
    (
        "Behaviour",
        lambda key: (
            key
            in {
                "action",
                "click",
                "enabled",
                "hidden",
                "toggle",
                "val",
                "min",
                "max",
                "start_value",
                "options",
                "swipe",
                "transition",
                "ext_click_h",
                "ext_click_v",
            }
        ),
    ),
]
OTHER_GROUP = "Other"


def group_properties(obj: Dict) -> List[Tuple[str, List[str]]]:
    """
    Sort the properties of an object into groups for the property editor.
    :return: (title, keys) for every group that has properties, keys in the order of the object
    """
    grouped: Dict[str, List[str]] = {title: [] for title, _ in _GROUPS}
    grouped[OTHER_GROUP] = []
    for key in obj:
        group = next((title for title, matches in _GROUPS if matches(key)), OTHER_GROUP)
        grouped[group].append(key)
    return [(title, keys) for title, keys in grouped.items() if keys]


def is_color_property(key: str) -> bool:
    return "color" in key
