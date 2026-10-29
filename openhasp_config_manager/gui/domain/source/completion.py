"""
What can be completed at the cursor in a file: property names of an object, the values of a property that takes one of a few
(`"mode": "dots"`, see `value_choices`), the variables inside of a template, the placeholders of openHASP in a `text` (`%ip%`, see
`placeholders.py`), and the path of an `!include`. Qt-free.
"""

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from openhasp_config_manager.gui.domain.object_type_docs import (
    COMMON_PROPERTIES,
    STYLE_PROPERTIES,
    TYPE_DOCS,
    is_text_property,
)
from openhasp_config_manager.gui.domain.source.docs import PROPERTY_DOCS
from openhasp_config_manager.gui.domain.source.placeholders import (
    PLACEHOLDER_PROPERTY,
    is_typed_placeholder,
    placeholder_candidates,
    typed_placeholder_end,
)
from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, tokenize_line
from openhasp_config_manager.gui.domain.style_parts import OBJECT_PARTS, Part, State, style_key
from openhasp_config_manager.validation.property_values import ValueChoice, value_choices

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


# the path of an `!include` that is being typed, up to the cursor
_INCLUDE_PATH = re.compile(r'"!include"\s*:\s*"([^"]*)$')
# the keys of a directive object besides the directive itself
DIRECTIVE_KEYS = ["for", "vars"]


@dataclass(frozen=True)
class CompletionContext:
    # what is being typed
    kind: str  # "property", "value", "variable", "placeholder" or "include" (the path of an `!include`)
    # the part of the word before the cursor
    prefix: str
    # where the word starts in the line
    start: int
    # whether the key has its opening quote already (a property is also completed before it is typed), or the value
    quoted: bool = True
    # the property of which the value is typed (kind "value")
    key: Optional[str] = None


@dataclass(frozen=True)
class Insertion:
    """What replaces the typed key when a property is chosen: columns of the line, and where the cursor goes."""

    start: int
    end: int
    text: str
    cursor: int


def completion_context(
    line_before_cursor: str, language: Language, inside_object: bool = False
) -> Optional[CompletionContext]:
    """
    :param inside_object: whether the cursor is in an object, only then a key is completed before its opening quote
    :return: what the text before the cursor asks to complete, None if nothing
    """
    line = line_before_cursor
    # JSON has no templates and no objects with properties
    if language in (Language.TEXT, Language.JSON):
        return None
    if language == Language.JSONL and (match := _INCLUDE_PATH.search(line)):
        return CompletionContext("include", match.group(1), match.start(1))
    open_template = _open_template(line)
    if open_template is not None:
        word_start = len(line)
        while word_start > open_template and (line[word_start - 1].isalnum() or line[word_start - 1] in "_."):
            word_start -= 1
        return CompletionContext("variable", line[word_start:], word_start)
    if language == Language.JSONL:
        if (start := _placeholder_start(line)) is not None:
            return CompletionContext("placeholder", line[start:], start)
        if (match := _VALUE.search(line)) is not None and _has_values(match["key"]) and not _in_comment(line, match.start()):
            quoted = match["quote"] == '"'
            return CompletionContext("value", match["prefix"], match.start("prefix") - quoted, quoted, match["key"])
        quote = _open_key_quote(line)
        if quote is not None:
            return CompletionContext("property", line[quote + 1 :], quote + 1)
        if inside_object and (start := _bare_key_start(line)) is not None:
            return CompletionContext("property", line[start:], start, quoted=False)
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


def _placeholder_start(line: str) -> Optional[int]:
    """
    :return: where a placeholder starts that is being typed: a `%` and letters at the start of the value of a `text` (openHASP only
        replaces a text that is the placeholder and nothing else), None if there is none
    """
    quote = line.rfind('"')
    if quote < 0 or not is_typed_placeholder(line[quote + 1 :]):
        return None
    tokens = [token for token in tokenize_line(line + '"', Language.JSONL) if token.start < quote]
    if len(tokens) < 2 or tokens[-1].text(line) != ":":
        return None
    key = tokens[-2]
    return quote + 1 if key.kind == TokenKind.KEY and key.text(line) == f'"{PLACEHOLDER_PROPERTY}"' else None


# the start of the value of a property: `"mode": "do` or `"bg_grad_dir": 1`
_VALUE = re.compile(r'"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"\s*:\s*(?P<quote>"?)(?P<prefix>[A-Za-z0-9_-]*)$')


def _in_comment(line: str, column: int) -> bool:
    return any(token.kind == TokenKind.COMMENT and token.start <= column for token in tokenize_line(line, Language.JSONL))


def _has_values(key: str) -> bool:
    """:return: whether a property takes one of a few values, for any object type"""
    return any(value_words(object_type, key) for object_type in (None, *TYPE_DOCS))


def value_words(object_type: Optional[str], key: str) -> List[str]:
    """:return: the values to offer for a property, as they are typed (`dots`, `0`, `true`), empty if it takes more than a few"""
    if key == "obj":
        return sorted(TYPE_DOCS)
    return [_word(choice) for choice in value_choices(object_type, key)]


def value_choice(object_type: Optional[str], key: str, word: str) -> Optional[ValueChoice]:
    """:return: the value of a property a word of `value_words` stands for"""
    if key == "obj" and word in TYPE_DOCS:
        return ValueChoice(word, f"a `{word}` object")
    return next((choice for choice in value_choices(object_type, key) if _word(choice) == word), None)


def _word(choice: ValueChoice) -> str:
    return str(choice.value).lower() if isinstance(choice.value, bool) else str(choice.value)


def value_insertion(line: str, column: int, context: CompletionContext, word: str, choice: ValueChoice) -> Insertion:
    """
    What to write when a value is chosen from the list: it replaces what is typed of it, also after the cursor, with the quotes a
    text needs (`"dots"`) and without them for a number or true/false, unless the value was started with a quote.
    """
    end = column + len(re.match(r"[A-Za-z0-9_-]*", line[column:])[0])
    if context.quoted or isinstance(choice.value, str):
        if line[end : end + 1] == '"':
            end += 1
        text = f'"{word}"'
    else:
        text = word
    return Insertion(context.start, end, text, context.start + len(text))


def placeholder_insertion(line: str, column: int, context: CompletionContext, word: str) -> Insertion:
    """What to write when a placeholder is chosen from the list: it replaces what is typed of it, also after the cursor."""
    return Insertion(context.start, typed_placeholder_end(line, column), word, context.start + len(word))


_BARE_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_NO_KEY_IN = (TokenKind.STRING, TokenKind.KEY, TokenKind.COLOR, TokenKind.TEMPLATE, TokenKind.COMMENT)


def _bare_key_start(line: str) -> Optional[int]:
    """:return: where a word without quotes starts that stands where a key goes (an empty word at the cursor), None if there is none"""
    match = _BARE_WORD.search(line)
    start = match.start() if match else len(line)
    before = line[:start].rstrip()
    if before and not before.endswith(("{", ",")):
        return None
    if any(token.kind in _NO_KEY_IN and token.start < start < token.end for token in tokenize_line(line, Language.JSONL)):
        return None
    return start


def property_insertion(
    line: str, column: int, context: CompletionContext, word: str, object_type: Optional[str] = None
) -> Insertion:
    """
    What to write when a property is chosen from the list: the key with its quotes, and unless the key has a value already the colon
    and the start of the value, so it can be typed right away (`"align": "|"` for text, `"x": |` for the rest).
    :param line: the text of the line, `column` the position of the cursor in it
    """
    end = column + len(re.match(r"[A-Za-z0-9_]*", line[column:])[0])
    if context.quoted and line[end : end + 1] == '"':
        end += 1
    has_value = line[end:].lstrip().startswith(":")
    text = ("" if context.quoted else '"') + word + '"'
    if has_value:
        return Insertion(context.start, end, text, context.start + len(text))
    if is_text_property(word, object_type):
        text += ': ""'
        return Insertion(context.start, end, text, context.start + len(text) - 1)
    text += ": "
    return Insertion(context.start, end, text, context.start + len(text))


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


def keys_for(object_type: Optional[str], prefix: str = "", present: Iterable[str] = (), directive: bool = False) -> List[str]:
    """
    :param directive: whether the object is a directive (`!include`): it has `vars` and `for`, not the properties of an object
    :return: the keys to offer in an object (see `properties_for`); `!include` too in an object that has no keys yet
    """
    present = list(present)
    if directive:
        return [key for key in DIRECTIVE_KEYS if key not in present]
    return properties_for(object_type, prefix, present) + ([] if present else ["!include"])


def complete(
    context: CompletionContext,
    properties: Iterable[str] = OBJECT_PROPERTIES,
    variables: Iterable[str] = (),
    paths: Iterable[str] = (),
    values: Iterable[str] = (),
) -> List[str]:
    """
    :param paths: the files an `!include` can name (see `include_targets`)
    :param values: the values of the property of which the value is typed (see `value_words`)
    :return: the words that start with the typed prefix, without the word that is already typed completely (a value stays: the
        list shows what it means)
    """
    if context.kind == "placeholder":
        return placeholder_candidates(context.prefix)
    if context.kind == "value":
        # in the order of their meaning (0, 1, 2 or left, center, right), the ones that start with what is typed
        return [word for word in values if word.lower().startswith(context.prefix.lower())]
    words = {"property": properties, "variable": variables, "include": paths}[context.kind]
    return sorted({word for word in words if word.startswith(context.prefix) and word != context.prefix})
