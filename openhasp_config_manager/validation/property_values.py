"""
The values openHASP accepts for its properties, from the source of openHASP 0.7.0-rc13 (`src/hasp/hasp_attribute.cpp`,
`hasp_parser.cpp`). The plate takes a value it doesn't know without an error and does something else with it:
- it ignores a name it doesn't know, e.g. a label with `"mode": "dot"` (instead of `dots`) keeps its previous mode
- it reads a number with `atoi` and casts it to the type of the property, so a value out of range wraps around (`"bg_opa": 300`
  is 44) and a text that isn't a number is 0 (`"clip_corner": true` is 0)
- it styles the main part or the default state instead of a part or state the object doesn't have (`"bg_color10"` on a label)
"""

import difflib
import re
from typing import Dict, FrozenSet, List, Optional, Tuple

# hasp_process_label_long_mode: the mode of a label, and of the label of a button
LABEL_MODES = ("expand", "break", "dots", "scroll", "loop", "crop")
# hasp_process_cpicker_mode
CPICKER_MODES = ("hue", "saturation", "value")
# attribute_common_align: a name, or its number (0 to 3). Any other text is read as a number, which makes it 0 (left).
ALIGN_NAMES = ("left", "center", "right", "auto")
ALIGN_NUMBERS = (0, 1, 2, 3)

# per object type (`obj`): the properties that take one of the names
_NAMES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "label": {"mode": LABEL_MODES},
    "btn": {"mode": LABEL_MODES},
    "cpicker": {"mode": CPICKER_MODES},
}

# Parser::is_true (ignoring case): anything else is false
_TRUE_NAMES = ("true", "on", "yes", "1")
_FALSE_NAMES = ("false", "off", "no", "0")

_INT16 = (-32768, 32767)
_OPA = (0, 255)

# the style properties (hasp_local_style_attr), which take a part and state suffix (`bg_color10`), and the range of the ones
# that are whole numbers (None: a color, font, text or image, or true/false)
_STYLE_RANGES: Dict[str, Optional[Tuple[int, int]]] = {
    **dict.fromkeys(
        (
            "bg_opa",
            "border_opa",
            "image_opa",
            "image_recolor_opa",
            "line_opa",
            "opa_scale",
            "outline_opa",
            "pattern_opa",
            "pattern_recolor_opa",
            "shadow_opa",
            "text_opa",
            "value_opa",
        ),
        _OPA,
    ),
    **dict.fromkeys(
        (
            "border_width",
            "line_dash_gap",
            "line_dash_width",
            "line_width",
            "margin_bottom",
            "margin_left",
            "margin_right",
            "margin_top",
            "outline_pad",
            "outline_width",
            "pad_bottom",
            "pad_inner",
            "pad_left",
            "pad_right",
            "pad_top",
            "radius",
            "scale_border_width",
            "scale_end_border_width",
            "scale_end_line_width",
            "scale_width",
            "shadow_ofs_x",
            "shadow_ofs_y",
            "shadow_spread",
            "shadow_width",
            "size",
            "text_letter_space",
            "text_line_space",
            "transform_height",
            "transform_width",
            "value_letter_space",
            "value_line_space",
            "value_ofs_x",
            "value_ofs_y",
        ),
        _INT16,
    ),
    # where the gradient starts and ends, of 255
    "bg_main_stop": _OPA,
    "bg_grad_stop": _OPA,
    # none, vertical, horizontal
    "bg_grad_dir": (0, 2),
    # normal, additive, subtractive
    "bg_blend_mode": (0, 2),
    # none, underline, strikethrough: bits
    "text_decor": (0, 3),
    # bottom 1, top 2, left 4, right 8, internal 16: bits
    "border_side": (0, 31),
    # lv_align_t: from center (0) to out right bottom (20)
    "value_align": (0, 20),
    # read as a number, not as true/false
    "clip_corner": (0, 1),
    **dict.fromkeys(
        (
            "bg_color",
            "bg_grad_color",
            "scale_grad_color",
            "scale_end_color",
            "text_color",
            "text_sel_color",
            "text_font",
            "border_color",
            "outline_color",
            "shadow_color",
            "line_color",
            "value_str",
            "value_color",
            "value_font",
            "pattern_recolor",
            "pattern_image",
            "image_recolor",
        ),
        None,
    ),
}
# style properties that are true or false (Parser::is_true)
_STYLE_BOOLS: FrozenSet[str] = frozenset({"border_post", "line_rounded", "pattern_repeat"})

# hasp_attribute_get_part_state_new: the parts (tens digit of a two digit suffix) each object type has. The plate styles the
# main part (0) instead of any other.
_PARTS: Dict[str, Tuple[int, ...]] = {
    **dict.fromkeys(("btn", "label", "led", "line", "linemeter", "img", "imgbtn", "obj", "tab", "qrcode"), (0,)),
    "btnmatrix": (0, 40),
    **dict.fromkeys(("slider", "switch", "arc"), (0, 10, 20)),
    **dict.fromkeys(("bar", "spinner", "checkbox"), (0, 10)),
    "cpicker": (0, 20),
    "roller": (0, 50),
    "dropdown": (0, 40, 50, 80),
    "gauge": (0, 10, 60),
    "msgbox": (0, 30, 40),
    "tabview": (0, 10, 30, 40, 50),
}
# the states (units digit): default, toggled, pressed, pressed and toggled, disabled, disabled and toggled. The plate styles the
# default state instead of 6 to 9.
STATES = range(6)

# properties of objects that are whole numbers in a range
_OBJECT_RANGES: Dict[str, Dict[str, Tuple[int, int]]] = {
    # the type of an arc, slider or spinner: the plate takes it modulo 3
    **{obj: {"type": (0, 2)} for obj in ("arc", "slider", "spinner")},
    # down, up, left, right
    "dropdown": {"direction": (0, 3)},
    "spinner": {"type": (0, 2), "direction": (0, 1)},
}
# HASP_NUM_PAGES of the ESP32 builds: page 0 (on top of all pages) and 1 to 12
PAGES = (0, 12)
# the objects that clamp their val to min and max (0 and 100 if they aren't set)
_RANGE_OBJECTS = frozenset({"bar", "slider", "arc", "gauge", "linemeter"})

_SUFFIX = re.compile(r"^(?P<name>[a-z_]+?)(?P<suffix>\d+)$")


def value_problems(obj: Dict, key: str) -> List[str]:
    """
    :param obj: a rendered object
    :param key: one of its properties
    :return: why the plate won't take the property as it is written, empty if it does (or the property isn't known here)
    """
    value = obj.get(key)
    if isinstance(value, str) and "{{" in value:
        # a template that can't be rendered, which is a problem of its own
        return []
    obj_type = obj.get("obj")

    match = _SUFFIX.match(key)
    name = match["name"] if match and match["name"] in _STYLE_RANGES.keys() | _STYLE_BOOLS else key
    if name in _STYLE_RANGES or name in _STYLE_BOOLS:
        problems = _suffix_problems(obj_type, match["suffix"]) if name != key else []
        if name in _STYLE_BOOLS:
            return problems + _bool_problems(value)
        if _STYLE_RANGES[name] is not None:
            return problems + _number_problems(value, _STYLE_RANGES[name])
        return problems

    if key == "align":
        return _align_problems(value)
    if key == "page":
        return _number_problems(value, PAGES)
    if key == "val" and obj_type in _RANGE_OBJECTS:
        return _val_problems(obj)
    names = _NAMES.get(obj_type, {}).get(key)
    if names is not None:
        return [] if isinstance(value, str) and value.lower() in names else [_not_one_of(value, names)]
    value_range = _OBJECT_RANGES.get(obj_type, {}).get(key)
    if value_range is not None:
        return _number_problems(value, value_range)
    return []


def _suffix_problems(obj_type: Optional[str], suffix: str) -> List[str]:
    """
    Only two digits are a part and a state: one digit is the older scheme (hasp_attribute_get_part_state_old), which means
    something else per object type.
    """
    if len(suffix) != 2:
        return []
    part, state = int(suffix) - int(suffix) % 10, int(suffix) % 10
    problems = []
    parts = _PARTS.get(obj_type)
    if parts is not None and part not in parts:
        listed = ", ".join(str(p) for p in parts)
        problems.append(f"a {obj_type} has no part {part} (its parts: {listed}), the plate styles its main part instead")
    if state not in STATES:
        problems.append(f"there is no state {state} (0 to 5), the plate styles the default state instead")
    return problems


def _number_problems(value, value_range: Tuple[int, int]) -> List[str]:
    low, high = value_range
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, str))
        or (isinstance(value, str) and not re.fullmatch(r"-?\d+", value))
    ):
        return [f"{value!r} is not a whole number from {low} to {high}, the plate reads it as {_atoi(value)}"]
    if not low <= int(value) <= high:
        return [f"{value} is not from {low} to {high}"]
    return []


def _atoi(value) -> int:
    """What the plate reads a value as (`atoi` of its text): the digits at its start, 0 if there are none."""
    text = "true" if value is True else "false" if value is False else str(value)
    match = re.match(r"\s*[-+]?\d+", text)
    return int(match.group()) if match else 0


def _bool_problems(value) -> List[str]:
    if isinstance(value, bool) or (isinstance(value, int) and value in (0, 1)):
        return []
    if isinstance(value, str) and value.lower() in _TRUE_NAMES + _FALSE_NAMES:
        return []
    return [f"{value!r} is not true or false (or on, off, yes, no, 1, 0), the plate reads it as false"]


def _align_problems(value) -> List[str]:
    # True would count as 1
    if isinstance(value, int) and not isinstance(value, bool) and value in ALIGN_NUMBERS:
        return []
    if isinstance(value, str) and (value.lower() in ALIGN_NAMES or (value.isdigit() and int(value) in ALIGN_NUMBERS)):
        return []
    return [_not_one_of(value, ALIGN_NAMES + ALIGN_NUMBERS)]


def _val_problems(obj: Dict) -> List[str]:
    numbers = [obj.get(key, default) for key, default in (("val", 0), ("min", 0), ("max", 100))]
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in numbers):
        return []
    val, low, high = numbers
    if low <= val <= high:
        return []
    return [f"{val} is not from min {low} to max {high}, the plate shows {min(max(val, low), high)}"]


def _not_one_of(value, allowed: Tuple) -> str:
    """e.g. `'dot' is not one of: expand, break, dots, scroll, loop, crop (did you mean 'dots'?)`"""
    text = f"{value!r} is not one of: {', '.join(str(name) for name in allowed)}"
    names = [name for name in allowed if isinstance(name, str)]
    close = difflib.get_close_matches(str(value).lower(), names, n=1) if isinstance(value, str) else []
    return f"{text} (did you mean {close[0]!r}?)" if close else text
