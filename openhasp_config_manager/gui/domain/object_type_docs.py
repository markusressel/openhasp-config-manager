"""
The properties of each openHASP object type, with the explanation of what they do for that type, for the completion and the hover
text of the text editor. Qt-free.

Source: https://www.openhasp.com/0.7.0/design/objects/ (one page per object type) and
https://www.openhasp.com/0.7.0/design/styling/. A property that means something else for a type (`mode`, `align`, `val`, `type`,
`angle`, ...) is explained here per type, the generic explanations are in `source_docs.PROPERTY_DOCS`.
"""

from typing import Dict, Optional

# the properties every object type has (https://www.openhasp.com/0.7.0/design/objects/)
COMMON_PROPERTIES = (
    "id", "obj", "page", "groupid", "x", "y", "w", "h", "enabled", "hidden", "opacity", "swipe", "action", "click", "ext_click_h",
    "ext_click_v", "parentid", "tag", "jsonl",
)  # fmt: skip

# the style properties (https://www.openhasp.com/0.7.0/design/styling/). They can end in two digits for the part and the state.
STYLE_PROPERTIES = (
    "radius", "clip_corner", "bg_opa", "bg_color", "bg_grad_color", "bg_grad_dir", "bg_grad_stop", "bg_main_stop", "border_color",
    "border_opa", "border_width", "border_side", "border_post", "outline_color", "outline_opa", "outline_width", "outline_pad",
    "pad_top", "pad_bottom", "pad_left", "pad_right", "pad_inner", "margin_top", "margin_bottom", "margin_left", "margin_right",
    "shadow_color", "shadow_opa", "shadow_width", "shadow_ofs_x", "shadow_ofs_y", "shadow_spread", "text_color", "text_opa",
    "text_font", "text_letter_space", "text_line_space", "text_decor", "text_sel_color", "value_str", "value_color", "value_opa",
    "value_font", "value_letter_space", "value_line_space", "value_align", "value_ofs_x", "value_ofs_y", "line_color", "line_opa",
    "line_width", "line_rounded", "line_dash_width", "line_dash_gap", "scale_grad_color", "scale_end_color", "scale_width",
    "scale_border_width", "scale_end_line_width", "scale_end_border_width", "image_opa", "image_recolor", "image_recolor_opa",
)  # fmt: skip

_VALUE_RANGE = "Can be negative."

# the properties of a type and what they do for it. `obj` types that are not here are not restricted (see `properties_of_type`).
TYPE_DOCS: Dict[str, Dict[str, str]] = {
    "btn": {
        "toggle": "Whether the button is a toggle button (on and off) instead of a normal push button.",
        "val": "The state of a toggle button: 0 not toggled, 1 toggled.",
        "text": "The text of the button. A character can get its own color with `#RRGGBB ` in front of it and `#` after it.",
        "mode": "What happens with a text that is too long: `expand` (the button grows), `break` (wrap lines), `dots`, `scroll`, "
        "`loop` (circular scroll) or `crop`.",
        "align": "Alignment of the text: `left`, `center` or `right`.",
    },
    "label": {
        "text": "The text. `\\n` is a line break.",
        "mode": "What happens with a text that is too long: `expand` (the label grows), `break` (wrap lines), `dots`, `scroll`, "
        "`loop` (circular scroll) or `crop` (the default).",
        "align": "Alignment of the text: `left`, `center` or `right`.",
    },
    "switch": {
        "val": "The state of the switch: 0 off, 1 on.",
    },
    "checkbox": {
        "val": "Whether the checkbox is checked: 0 or 1.",
        "text": "The label of the checkbox. The size comes from the font and the text, `w` and `h` are ignored.",
    },
    "slider": {
        "min": f"The smallest value. {_VALUE_RANGE}",
        "max": f"The largest value. {_VALUE_RANGE}",
        "val": f"The current value. {_VALUE_RANGE}",
        "start_value": f"The start of the filled part of the slider (the smallest allowed value). {_VALUE_RANGE}",
    },
    "bar": {
        "min": f"The smallest value. {_VALUE_RANGE}",
        "max": f"The largest value. {_VALUE_RANGE}",
        "val": f"The current value. {_VALUE_RANGE}",
        "start_value": f"The start of the filled part of the bar (the smallest allowed value). {_VALUE_RANGE}",
    },
    "arc": {
        "min": f"The smallest value. {_VALUE_RANGE}",
        "max": f"The largest value. {_VALUE_RANGE}",
        "val": f"The current value. {_VALUE_RANGE}",
        "rotation": "Rotates the arc: the offset to the 0 degree position.",
        "type": "How the arc is filled: 0 normal, 1 symmetrical, 2 reverse.",
        "adjustable": "Adds a knob that can be dragged to change the value.",
        "start_angle": "Where the background of the arc starts, 0 to 360 degrees.",
        "end_angle": "Where the background of the arc ends, 0 to 360 degrees.",
        "start_angle10": "Where the indicator of the arc starts, 0 to 360 degrees (style part 10).",
        "end_angle10": "Where the indicator of the arc ends, 0 to 360 degrees (style part 10).",
        "pad_top20": "Top padding that sizes the knob (style part 20).",
        "pad_bottom20": "Bottom padding that sizes the knob (style part 20).",
        "pad_left20": "Left padding that sizes the knob (style part 20).",
        "pad_right20": "Right padding that sizes the knob (style part 20).",
    },
    "dropdown": {
        "options": "The entries of the list, separated by `\\n`.",
        "val": "The index of the selected entry.",
        "text": "The text of the selected entry. Read only.",
        "direction": "The direction the list opens: 0 down, 1 up, 2 left, 3 right. Up and down can be overridden by the screen size.",
        "show_selected": "Whether the selected entry is shown (true), or a fixed text (false).",
        "max_height": "The largest height of the open list. Three quarters of the screen height by default.",
    },
    "roller": {
        "options": "The entries of the roller, separated by `\\n`.",
        "val": "The index of the selected entry.",
        "text": "The text of the selected entry. Read only.",
        "rows": "The number of visible rows (3 by default). Use it instead of `h`.",
        "mode": "0 normal (finite), 1 infinite.",
        "align": "Alignment of the text: `left`, `center` (the default) or `right`.",
    },
    "gauge": {
        "min": "The smallest value (0 by default).",
        "max": "The largest value (100 by default).",
        "val": "The current value.",
        "critical_value": "From this value on the scale has the color `scale_end_color` (80 by default).",
        "label_count": "The number of labels and major ticks of the scale.",
        "line_count": "The number of minor ticks of the whole scale (31 by default).",
        "angle": "The angle between the start and the end of the scale, 0 to 360 (240 by default).",
        "rotation": "Rotates the gauge: the offset of the angles, 0 to 360.",
        "format": "A divisor for the values of the major ticks, 0 to 4.",
    },
    "linemeter": {
        "min": f"The smallest value (0 by default). {_VALUE_RANGE}",
        "max": f"The largest value (100 by default). {_VALUE_RANGE}",
        "val": f"The current value. {_VALUE_RANGE}",
        "angle": "The angle between the start and the end of the scale, 0 to 360 (240 by default).",
        "line_count": "The number of ticks of the scale (31 by default).",
        "rotation": "Rotates the scale: the offset of the angles, 0 to 360.",
        "type": "The direction of the indicator line: 0 clockwise, 1 counter-clockwise.",
    },
    "tabview": {
        "val": "The number of the active tab, starting at 0.",
        "text": "The name of the active tab.",
        "btn_pos": "Where the tab buttons are: 0 none, 1 top (the default), 2 bottom, 3 left, 4 right.",
        "count": "The number of tabs. Read only.",
    },
    "cpicker": {
        "color": "The selected color, as `#rrggbb`.",
        "scale_width": "Width of the ring of colors (25 by default).",
        "pad_inner": "Space between the ring and the circle with the preview in it (10 by default).",
        "mode": "What the picker changes: `hue`, `saturation` or `value`.",
        "mode_fixed": "Whether a long press can not switch between the modes.",
    },
    "spinner": {
        "speed": "How long one rotation takes, in milliseconds (1000 by default).",
        "direction": "The direction of the rotation: 0 clockwise, 1 counter-clockwise.",
        "angle": "The length of the spinning segment in degrees, 0 to 360 (60 by default).",
        "type": "The animation: 0 slows down at the top, 1 slows down and stretches, 2 constant speed without stretching.",
        "line_width": "Width of the background circle (20 by default).",
        "line_color": "Color of the background circle.",
    },
    "led": {
        "val": "The brightness of the LED, 0 to 255.",
    },
    "btnmatrix": {
        "options": 'The labels of the buttons, as a list of strings. `"\\n"` starts a new row of buttons.',
        "align": "Alignment of the text: `left`, `center` (the default) or `right`.",
        "toggle": "Whether all buttons are toggle buttons.",
        "one_check": "Whether only one button can be checked at a time.",
        "val": "The number of the active button, starting at 0. -1 deactivates all buttons (with `toggle` and `one_check`).",
    },
    "msgbox": {
        "text": "The text of the message.",
        "options": 'The labels of the buttons, as a list of strings (`["OK"]` by default).',
        "modal": "Whether the message has to be answered before anything else can be touched.",
        "auto_close": "Closes the message after this many milliseconds.",
    },
    "line": {
        "points": "The points of the line, as a list of `[x, y]` pairs, e.g. `[[10,25],[100,25],[100,0]]`.",
        "auto_size": "Whether the size of the object follows the points (the default).",
        "y_invert": "Inverts the y coordinates, if the direction of y seems the wrong way round.",
    },
    "img": {
        "src": "The image to show, e.g. `L:/image.png`. The file has to be on the plate.",
        "auto_size": "Whether the object takes the size of the image (the default).",
        "offset_x": "Moves the picture horizontally inside the object.",
        "offset_y": "Moves the picture vertically inside the object.",
        "zoom": "Scale of the image: 256 is the normal size, 512 double, 128 half.",
        "angle": "Rotation of the image in 0.1 degrees, so 45.8 degrees is 458.",
        "pivot_x": "The horizontal point the image rotates around (the center by default).",
        "pivot_y": "The vertical point the image rotates around (the center by default).",
        "antialias": "Better quality of zoom and rotation, but slower.",
    },
    "qrcode": {
        "text": "The content of the QR code. At most 122 characters with the default version 7.",
        "size": "Width and height of the square object (140 by default).",
    },
    "obj": {},
}


# properties whose value is text. The style properties with `color` in their name are as well.
_TEXT_PROPERTIES = frozenset({"text", "align", "mode", "obj", "src", "value_str", "action", "options"})
# what is text for most types, but not for these: the options of a roller or dropdown are text, those of a button matrix a list
_NOT_TEXT = {("options", "btnmatrix"), ("options", "msgbox"), ("mode", "roller")}


def is_text_property(name: str, object_type: Optional[str] = None) -> bool:
    """:return: whether the value of a property is written as a string (`"align": "left"`), not as a number, a bool or a list"""
    base = name[:-2] if len(name) > 2 and name[-2:].isdigit() else name
    if (base, object_type) in _NOT_TEXT:
        return False
    return "color" in base or base in _TEXT_PROPERTIES
