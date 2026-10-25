"""Short explanations of the properties of openHASP objects, for the hover text of the text editor. Qt-free."""

import re
from typing import Optional

# https://www.openhasp.com/latest/design/objects/ and https://www.openhasp.com/latest/design/styling/
PROPERTY_DOCS = {
    "page": "The page the object is on (1 to 12, 0 for all pages). Objects without a page are on the page of the object before them.",
    "id": "The id of the object on its page. The object is `p<page>b<id>`. Id 0 changes the settings of the page itself "
    "(`prev`, `next`, `back`, `bg_color`, ...).",
    "obj": "The type of the object: `btn`, `label`, `switch`, `checkbox`, `slider`, `bar`, `arc`, `led`, `img`, `cont`, ...",
    "parentid": "The id of an object on the same page that contains this one. Position and size are relative to it.",
    "groupid": "The group of the object. Objects of a group send their state to the same topic, e.g. radio buttons.",
    "x": 'Distance from the left edge in pixels, or in percent of the width of the parent (`"50%"`).',
    "y": 'Distance from the top edge in pixels, or in percent of the height of the parent (`"50%"`).',
    "w": 'Width in pixels, or in percent of the width of the parent (`"33%"`).',
    "h": 'Height in pixels, or in percent of the height of the parent (`"33%"`).',
    "action": "What touching the object does for the page: `prev`, `next`, `back`, a page number, or a command.",
    "text": "The text of the object.",
    "align": "Alignment of the text: 0 left, 1 center, 2 right.",
    "mode": "How the text or the image is shown, e.g. `dots`, `break`, `expand`, `crop`, `scroll`, `circular`.",
    "val": "The value of the object: the position of a slider or arc, the state of a switch, the selected option.",
    "min": "The smallest value of the object.",
    "max": "The largest value of the object.",
    "options": "The entries of a dropdown or roller, separated by `\\n`.",
    "enabled": "Whether the object reacts to touch.",
    "hidden": "Whether the object is hidden.",
    "click": "Whether the object can be clicked.",
    "toggle": "Whether the button keeps its state after a click.",
    "swipe": "Whether the object sends swipe events.",
    "src": "The image to show, e.g. `L:/image.png`. The file has to be on the plate.",
    "zoom": "Scale of an image, 256 is 100 %.",
    "angle": "Rotation of an image in 0.1 degrees.",
    "radius": "Corner radius in pixels.",
    "opacity": "Opacity of the whole object, 0 to 255.",
    "bg_color": 'Background color, e.g. `"#ff8800"` or a color name.',
    "bg_opa": "Opacity of the background, 0 to 255.",
    "bg_grad_color": "End color of the background gradient.",
    "bg_grad_dir": "Direction of the background gradient: 0 none, 1 vertical, 2 horizontal.",
    "bg_main_stop": "Where the gradient starts, 0 to 255.",
    "bg_grad_stop": "Where the gradient ends, 0 to 255.",
    "border_color": "Color of the border.",
    "border_width": "Width of the border in pixels.",
    "border_side": "Sides with a border: 0 none, 1 bottom, 2 top, 4 left, 8 right, 15 all (added together).",
    "border_opa": "Opacity of the border, 0 to 255.",
    "outline_color": "Color of the outline.",
    "outline_width": "Width of the outline in pixels.",
    "outline_pad": "Distance between the outline and the object.",
    "shadow_color": "Color of the shadow.",
    "shadow_width": "Blur of the shadow in pixels.",
    "shadow_ofs_x": "Horizontal offset of the shadow.",
    "shadow_ofs_y": "Vertical offset of the shadow.",
    "shadow_spread": "Size of the shadow in addition to the object.",
    "pad_top": "Space between the top edge and the content.",
    "pad_bottom": "Space between the bottom edge and the content.",
    "pad_left": "Space between the left edge and the content.",
    "pad_right": "Space between the right edge and the content.",
    "pad_inner": "Space between the children of the object.",
    "text_color": "Color of the text.",
    "text_font": "Size of the font, as it is on the plate (e.g. 12, 16, 22, 28).",
    "text_opa": "Opacity of the text, 0 to 255.",
    "text_letter_space": "Space between letters in pixels.",
    "text_line_space": "Space between lines in pixels.",
    "text_decor": "Text decoration: 0 none, 1 underline, 2 strike through.",
    "line_width": "Width of lines in pixels.",
    "line_color": "Color of lines.",
    "line_rounded": "Whether line ends are rounded.",
    "value_str": "A second text that is shown next to the object.",
    "value_font": "Font size of `value_str`.",
    "value_color": "Color of `value_str`.",
    "rows": "Number of rows.",
    "cols": "Number of columns.",
    "start_angle": "Where an arc starts, in degrees.",
    "end_angle": "Where an arc ends, in degrees.",
    "rotation": "Rotation of the arc in degrees.",
    "tag": "Any data. It is sent with every event of the object.",
    "ext_click_h": "Makes the clickable area wider by this many pixels on both sides.",
    "ext_click_v": "Makes the clickable area taller by this many pixels on both sides.",
    "prev": "Page of the page settings (id 0): the page to go to when navigating back from the first page.",
    "next": "Page of the page settings (id 0): the page to go to when navigating forward from the last page.",
    "back": "Page of the page settings (id 0): the page the `back` action goes to.",
}

# https://www.openhasp.com/0.7.0/design/styling/: a style property can end in two digits, the part and the state of the object
_PARTS = {
    0: "the main part of the object (the background)",
    1: "the indicator or needle, highlighting the current value",
    2: "the knob which can be used to change the value",
    3: "the background of the items/buttons",
    4: "the items/buttons",
    5: "the selected item",
    6: "the major ticks of the gauge",
    7: "the text cursor",
    8: "the scrollbar",
    9: "another special part",
}
_STATES = {
    0: "default",
    1: "toggled",
    2: "pressed, not toggled",
    3: "pressed and toggled",
    4: "disabled, not toggled",
    5: "disabled and toggled",
}
# what the parts are for the objects that say so in their documentation (https://www.openhasp.com/0.7.0/design/objects/)
_OBJECT_PARTS = {
    "switch": {1: "the indicator (the colored track)", 2: "the knob"},
    "arc": {1: "the indicator arc", 2: "the knob"},
    "spinner": {0: "the background circle", 1: "the spinning segment"},
    "tabview": {4: "the tab buttons"},
}

_SUFFIXED = re.compile(r"^(?P<base>.+?)(?P<part>\d)(?P<state>\d)$")


def describe_property(name: str, object_type: Optional[str] = None) -> Optional[str]:
    """
    :param object_type: the `obj` of the object the property is in, for what its parts are
    :return: what a property is, None if it is not known. A style property can end in two digits for the part and the state of
        the object (`bg_color12` is the background color of the indicator while pressed), which are explained as well.
    """
    if name in PROPERTY_DOCS:
        return PROPERTY_DOCS[name]
    match = _SUFFIXED.match(name)
    if not match or match["base"] not in PROPERTY_DOCS:
        return None
    part, state = int(match["part"]), int(match["state"])
    part_text = _OBJECT_PARTS.get(object_type or "", {}).get(part) or _PARTS[part]
    lines = [PROPERTY_DOCS[match["base"]], f"Suffix `{match['part']}{match['state']}`: part {part} is {part_text}"]
    if state in _STATES:
        lines[-1] += f"; state {state} is {_STATES[state]}"
    return "\n".join(lines) + "."
