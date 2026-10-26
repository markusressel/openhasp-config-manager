"""What can be completed at the cursor in a file: property names of an object, and the variables inside of a template. Qt-free."""

from dataclasses import dataclass
from typing import Iterable, List, Optional

from openhasp_config_manager.gui.domain.object_type_docs import COMMON_PROPERTIES, STYLE_PROPERTIES, TYPE_DOCS
from openhasp_config_manager.gui.domain.source_docs import PROPERTY_DOCS
from openhasp_config_manager.gui.domain.source_syntax import Language, TokenKind, tokenize_line
from openhasp_config_manager.gui.domain.style_parts import OBJECT_PARTS, Part, State, style_key

# the properties of openHASP objects (https://www.openhasp.com/0.7.0/design/objects/), for the keys of an object, and every
# property that has an explanation
_ALL_PROPERTIES = (
    {
        "page", "id", "obj", "parentid", "groupid", "x", "y", "w", "h", "action", "text", "align", "mode", "val", "min", "max",
        "start_value", "options", "enabled", "hidden", "click", "toggle", "swipe", "src", "zoom", "angle", "radius",
        "opacity", "ext_click_h", "ext_click_v", "bg_color", "bg_opa", "bg_grad_color", "bg_grad_dir", "bg_main_stop",
        "bg_grad_stop", "border_color", "border_width", "border_side", "border_opa", "outline_color",
        "outline_width", "outline_opa", "outline_pad", "shadow_color", "shadow_width", "shadow_ofs_x", "shadow_ofs_y",
        "shadow_spread", "shadow_opa", "pad_top", "pad_bottom", "pad_left", "pad_right", "pad_inner", "text_color", "text_font",
        "text_opa", "text_letter_space", "text_line_space", "text_decor", "line_width", "line_color", "line_opa", "line_rounded",
        "value_font", "value_color", "value_str", "value_ofs_x", "value_ofs_y", "value_align", "image_recolor",
        "image_recolor_opa", "image_opa", "scale_width", "scale_end_line_width", "scale_end_border_width", "scale_grad_color",
        "scale_end_color", "rows", "adjustable", "start_angle", "end_angle", "rotation", "type", "points",
    }
    | PROPERTY_DOCS.keys()
    | set(COMMON_PROPERTIES)
    | set(STYLE_PROPERTIES)
    | {name for docs in TYPE_DOCS.values() for name in docs}
)  # fmt: skip


def _is_style_variant(name: str) -> bool:
    """:return: whether a name is a style property with the digits for the part and the state (`bg_color10`)"""
    return len(name) > 2 and name[-2:].isdigit() and name[:-2] in STYLE_PROPERTIES


# every property, for objects of which the type is not known. The style properties with part and state are not listed, they
# are offered when the typed text starts with the property (see `properties_for`)
OBJECT_PROPERTIES = sorted(name for name in _ALL_PROPERTIES if not _is_style_variant(name))


@dataclass(frozen=True)
class CompletionContext:
    # what is being typed
    kind: str  # "property" or "variable"
    # the part of the word before the cursor
    prefix: str
    # where the word starts in the line
    start: int


def completion_context(line_before_cursor: str, language: Language) -> Optional[CompletionContext]:
    """:return: what the text before the cursor asks to complete, None if nothing"""
    line = line_before_cursor
    if language == Language.TEXT:
        return None
    open_template = _open_template(line)
    if open_template is not None:
        word_start = len(line)
        while word_start > open_template and (line[word_start - 1].isalnum() or line[word_start - 1] in "_."):
            word_start -= 1
        return CompletionContext("variable", line[word_start:], word_start)
    if language == Language.JSONL:
        quote = _open_key_quote(line)
        if quote is not None:
            return CompletionContext("property", line[quote + 1 :], quote + 1)
    return None


def _open_template(line: str) -> Optional[int]:
    """:return: where the body of a template that is not closed at the end of the line starts"""
    start = line.rfind("{{")
    if start < 0 or line.find("}}", start) >= 0:
        return None
    return start + 2


def _open_key_quote(line: str) -> Optional[int]:
    """:return: the index of the quote of a string that is not closed and stands where a key goes"""
    tokens = tokenize_line(line + '"', Language.JSONL)
    last_quote = None
    for token in tokens:
        if token.kind in (TokenKind.STRING, TokenKind.KEY, TokenKind.COLOR) and line[token.start : token.start + 1] == '"':
            if token.end > len(line):
                last_quote = token.start
    if last_quote is None:
        return None
    before = line[:last_quote].rstrip()
    return last_quote if before == "" or before.endswith(("{", ",")) else None


def properties_for(object_type: Optional[str], prefix: str = "", present: Iterable[str] = ()) -> List[str]:
    """
    The properties that make sense for an object type: those every object has, the style properties, and those of the type.
    A type that is not known (or not written yet) gets every property. A style property can end in two digits for the part and the
    state, these are offered once the typed prefix starts with a style property (`bg_color1` offers `bg_color10`, `bg_color12`, ...)
    and only for the parts the type is known to have.
    :param present: the properties the object has already, they are not offered again
    """
    if object_type in TYPE_DOCS:
        names = {*COMMON_PROPERTIES, *STYLE_PROPERTIES, *TYPE_DOCS[object_type]}
        # the parts are only known for some types (`OBJECT_PARTS`), the other ones can have any
        parts = [Part.MAIN, *OBJECT_PARTS[object_type]] if object_type in OBJECT_PARTS else list(Part)
    else:
        names = set(OBJECT_PROPERTIES)
        parts = list(Part)
    names.update(
        style_key(base, part, state)
        for base in STYLE_PROPERTIES
        if prefix.startswith(base)
        for part in parts
        for state in State
    )
    return sorted(names - set(present))


def complete(
    context: CompletionContext, properties: Iterable[str] = OBJECT_PROPERTIES, variables: Iterable[str] = ()
) -> List[str]:
    """:return: the words that start with the typed prefix, without the word that is already typed completely"""
    words = properties if context.kind == "property" else variables
    return sorted({word for word in words if word.startswith(context.prefix) and word != context.prefix})
