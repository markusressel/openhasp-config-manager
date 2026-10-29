"""
Short explanations of the properties of openHASP objects and of the directives of openhasp-config-manager (`!include`), for the
hover text of the text editor. Qt-free.
"""

import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from openhasp_config_manager.gui.domain.object_type_docs import COMMON_PROPERTIES, STYLE_PROPERTIES, TYPE_DOCS
from openhasp_config_manager.gui.domain.source.objects import SourceObject, object_at_line
from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, tokenize_line
from openhasp_config_manager.gui.domain.variables.definitions import key_at
from openhasp_config_manager.gui.domain.style_parts import OBJECT_PARTS, PART_DESCRIPTIONS, STATE_DESCRIPTIONS, Part, State

# https://www.openhasp.com/latest/design/objects/ and https://www.openhasp.com/latest/design/styling/
PROPERTY_DOCS = {
    "page": "The page the object is on (1 to 12, 0 for all pages). Objects without a page are on the page of the object before them.",
    "id": "The id of the object on its page. The object is `p<page>b<id>`. Id 0 changes the settings of the page itself "
    "(`prev`, `next`, `back`, `bg_color`, ...).",
    "obj": "The type of the object: `btn`, `label`, `switch`, `checkbox`, `slider`, `bar`, `arc`, `led`, `img`, `cont`, ...",
    "parentid": "The id of an object on the same page that contains this one. Position and size are relative to it.",
    "groupid": "The id of the GPIO group (0 to 15) the object belongs to. 0 means none.",
    "x": 'Distance from the left edge in pixels, or in percent of the width of the parent (`"50%"`).',
    "y": 'Distance from the top edge in pixels, or in percent of the height of the parent (`"50%"`).',
    "w": 'Width in pixels, or in percent of the width of the parent (`"33%"`).',
    "h": 'Height in pixels, or in percent of the height of the parent (`"33%"`).',
    "action": "What touching the object does for the page: `prev`, `next`, `back`, a page number, or a command.",
    "text": "The text of the object.",
    "align": "Alignment of the text: `left`, `center` or `right`.",
    "mode": "How the text or the image is shown, e.g. `dots`, `break`, `expand`, `crop`, `scroll`, `circular`.",
    "val": "The value of the object: the position of a slider or arc, the state of a switch, the selected option.",
    "min": "The smallest value of the object.",
    "max": "The largest value of the object.",
    "options": "The entries of a dropdown or roller, separated by `\\n`.",
    "enabled": "Whether the object can be touched. If it is not, the disabled style is used (state 4).",
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
    "text_font": "The id of the font, as it is on the plate.",
    "text_opa": "Opacity of the text, 0 to 255.",
    "text_letter_space": "Space between letters in pixels.",
    "text_line_space": "Space between lines in pixels.",
    "text_decor": "Text decoration: 0 none, 1 underline, 2 strike through.",
    "line_width": "Width of lines in pixels.",
    "line_color": "Color of lines.",
    "line_rounded": "Whether line ends are rounded.",
    "value_str": "A second text that is shown next to the object.",
    "value_font": "The id of the font of `value_str`.",
    "value_color": "Color of `value_str`.",
    "rows": "Number of rows.",
    "cols": "Number of columns.",
    "start_angle": "Where an arc starts, in degrees.",
    "end_angle": "Where an arc ends, in degrees.",
    "rotation": "Rotation of the arc in degrees.",
    "jsonl": "Sets several properties of an existing object at once, from a JSON object.",
    "clip_corner": "Clips what overflows the object at its rounded corners.",
    "border_post": "Draws the border after all children, so it is on top of them.",
    "outline_opa": "Opacity of the outline, 0 to 255.",
    "margin_top": "Space above the object.",
    "margin_bottom": "Space below the object.",
    "margin_left": "Space left of the object.",
    "margin_right": "Space right of the object.",
    "shadow_opa": "Opacity of the shadow, 0 to 255.",
    "text_sel_color": "Background color of selected text.",
    "value_opa": "Opacity of `value_str`, 0 to 255.",
    "value_letter_space": "Space between the letters of `value_str`, can be negative.",
    "value_line_space": "Space between the lines of `value_str`, can be negative.",
    "value_align": "Where `value_str` is: centered by default.",
    "value_ofs_x": "Horizontal offset of `value_str` from its position.",
    "value_ofs_y": "Vertical offset of `value_str` from its position.",
    "line_opa": "Opacity of lines, 0 to 255.",
    "line_dash_width": "Length of the dashes of horizontal and vertical lines. 0 means no dashes.",
    "line_dash_gap": "Gap between the dashes of horizontal and vertical lines. 0 means no dashes.",
    "scale_grad_color": "The color the lines of a scale change to, or the color of the minor ticks of a gauge.",
    "scale_end_color": "Color of the lines of a scale in the end region, or of the minor ticks and the critical area of a gauge.",
    "scale_width": "Width of a scale in the normal region, or length of the minor ticks of a gauge.",
    "scale_border_width": "Width of the border on the outer side of a scale in the normal region.",
    "scale_end_line_width": "Width of the lines of a scale in the end region.",
    "scale_end_border_width": "Width of the border on the outer side of a scale in the end region.",
    "image_opa": "Opacity of an image, 0 to 255.",
    "image_recolor": "Color of an overlay on the image.",
    "image_recolor_opa": "Opacity of the overlay of `image_recolor`, 0 to 255.",
    "tag": "Any data. It is sent with every event of the object.",
    "ext_click_h": "Makes the clickable area wider by this many pixels on both sides.",
    "ext_click_v": "Makes the clickable area taller by this many pixels on both sides.",
    "prev": "Page of the page settings (id 0): the page to go to when navigating back from the first page.",
    "next": "Page of the page settings (id 0): the page to go to when navigating forward from the last page.",
    "back": "Page of the page settings (id 0): the page the `back` action goes to.",
}

_SUFFIXED = re.compile(r"^(?P<base>.+?)(?P<part>\d)(?P<state>\d)$")


def _documented(name: str, object_type: Optional[str]) -> Optional[str]:
    """
    :return: the explanation of a property without suffix: what it means for the object type, else the generic one. Without a known
        type, a property that only some types have is explained for each of them.
    """
    if object_type in TYPE_DOCS and name in TYPE_DOCS[object_type]:
        return TYPE_DOCS[object_type][name]
    if name in PROPERTY_DOCS:
        return PROPERTY_DOCS[name]
    if object_type in TYPE_DOCS:
        return None
    by_text: Dict[str, List[str]] = {}
    for type_name, docs in TYPE_DOCS.items():
        if name in docs:
            by_text.setdefault(docs[name], []).append(type_name)
    if not by_text:
        return None
    if len(by_text) == 1:
        return next(iter(by_text))
    return "\n".join(f"{', '.join(f'`{type_name}`' for type_name in types)}: {text}" for text, types in by_text.items())


_DOCS_URL = "https://www.openhasp.com/0.7.0/design/"
_INCLUDE_URL = "https://github.com/markusressel/openhasp-config-manager#including-objects"

# the directive and its keys (see `processing/jsonl/includes.py`)
DIRECTIVE_DOCS = {
    "!include": "Replaced by the objects of another .jsonl file (a part), before anything is sent to the plate. The path is "
    "relative to the config directory, e.g. `common/parts/tile.jsonl`. The part uses variables for what differs between its "
    'instances, e.g. `"id": "{{ id }}"`. An object is either an openHASP object or a directive.',
    "vars": 'The variables of the part for this `!include`, e.g. `{"id": 29, "caption": "Elapsed"}`. They win over the '
    "variables of the file and of the folders of the part. A value can be a template, rendered with the variables of the file.",
    "for": 'Include the part once for every value: `{"column": [0, 1, 2]}` or `{"dot": "{{ range(1, 6) }}"}`. With several '
    "names, once for every combination (the first name changes slowest). The values win over `vars`.",
}


@dataclass(frozen=True)
class PropertyHelp:
    """What the text editor shows about a property: in the card of the hover and next to the completion list."""

    name: str
    # what the property does. Parts in `backticks` are code.
    summary: str
    # what kind of property it is, e.g. "Style property" or "slider property"
    kind: str
    # (label, text) pairs about the suffix of a style property: its part and its state
    details: List[Tuple[str, str]] = field(default_factory=list)
    # the page of the documentation of openHASP about it
    url: Optional[str] = None


def _kind_and_url(base: str, object_type: Optional[str]) -> Tuple[str, str]:
    if base in STYLE_PROPERTIES:
        return "Style property", _DOCS_URL + "styling/"
    if object_type in TYPE_DOCS and base in TYPE_DOCS[object_type]:
        return f"{object_type} property", f"{_DOCS_URL}objects/{object_type}/"
    if base in COMMON_PROPERTIES:
        return "Property of every object", _DOCS_URL + "objects/"
    return "Property", _DOCS_URL + "objects/"


def property_help(name: str, object_type: Optional[str] = None) -> Optional[PropertyHelp]:
    """
    :param object_type: the `obj` of the object the property is in, for what it means and what its parts are
    :return: what a property is and does, None if it is not known. A style property can end in two digits for the part and the
        state of the object (`bg_color12` is the background color of the indicator while pressed), which are explained as details.
    """
    if (text := _documented(name, object_type)) is not None:
        kind, url = _kind_and_url(name, object_type)
        return PropertyHelp(name, text, kind, [], url)
    match = _SUFFIXED.match(name)
    if not match or (base_text := _documented(match["base"], object_type)) is None:
        return None
    part, state = Part(int(match["part"])), int(match["state"])
    kind, url = _kind_and_url(match["base"], object_type)
    details = [("Part", f"{int(part)}: {OBJECT_PARTS.get(object_type or '', {}).get(part) or PART_DESCRIPTIONS[part]}")]
    if state in State:
        details.append(("State", f"{state}: {STATE_DESCRIPTIONS[State(state)]}"))
    return PropertyHelp(name, base_text, kind, details, url)


def directive_help(name: str) -> Optional[PropertyHelp]:
    """:return: what a key of a directive object is (`!include`, `vars`, `for`), None if it is none of them"""
    if name.startswith("!") and name not in DIRECTIVE_DOCS:
        return PropertyHelp(name, "Unknown directive: the only directive is `!include`.", "Directive", [], _INCLUDE_URL)
    if name not in DIRECTIVE_DOCS:
        return None
    kind = "Directive" if name.startswith("!") else "Key of an `!include`"
    return PropertyHelp(name, DIRECTIVE_DOCS[name], kind, [], _INCLUDE_URL)


def object_type_at_line(objects: List[SourceObject], line_number: int) -> Optional[str]:
    """:return: the `obj` of the object the line (starting at 1) is in, None if there is no object or it has no (single line) type"""
    found = object_at_line(objects, line_number)
    if found is None or found.get("obj") is None:
        return None
    return (found.get("obj").value or "").strip('"') or None


def help_at(objects: List[SourceObject], line: str, line_number: int, column: int) -> Optional[PropertyHelp]:
    """
    :param objects: the objects of the .jsonl text (see `scan_objects`), for the type of the object the line is in
    :param line: the text of the line, `line_number` its number (starting at 1)
    :return: the help for the property whose key is at a column, None if there is none or it is not known
    """
    for token in tokenize_line(line, Language.JSONL):
        if token.kind in (TokenKind.KEY, TokenKind.DIRECTIVE) and token.start <= column <= token.end:
            name = token.text(line).strip('"')
            found = object_at_line(objects, line_number)
            if name.startswith("!") or (found is not None and found.is_directive):
                return directive_help(name)
            return property_help(name, object_type_at_line(objects, line_number))
    return None


def theme_help_at(text: str, line: int, column: int) -> Optional[PropertyHelp]:
    """
    :param text: the text of a variable file (it may not be saved)
    :param line: starting at 1, `column` starting at 0
    :return: the help for the key of a default property of the theme of an object type (`theme.obj.btn.bg_color04`), what it means
        for that type, None if the key is something else or the property is not known
    """
    key = key_at(text, line, column)
    parts = key.name.split(".") if key else []
    if len(parts) != 4 or parts[:2] != ["theme", "obj"]:
        return None
    object_type, name = parts[2], parts[3]
    found = property_help(name, object_type)
    if found is None:
        return None
    default = ("Default", f"for every `{object_type}` object that doesn't set `{name}` itself")
    return replace(found, details=[default, *found.details])
