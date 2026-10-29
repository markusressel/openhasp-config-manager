"""
The syntax of the files of a config directory, for the text editor: which part of a line is a key, a string, a template,
a comment, ... It knows the dialect of the .jsonl files (one object after the other, `//` comments, trailing commas, Jinja2
templates in the strings, the placeholders of openHASP like `"text": "%ip%"`) that no JSON highlighter does. Qt-free, so it is tested without a display.
"""

import re
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import List, Optional

from openhasp_config_manager.gui.domain.source.placeholders import PLACEHOLDER_PROPERTY, placeholder_of
from openhasp_config_manager.processing.template_rendering import template_spans


class Language(Enum):
    JSONL = "jsonl"
    # plain JSON, like a device's `config.json`: highlighted like JSONL, but not checked as objects
    JSON = "json"
    CMD = "cmd"
    YAML = "yaml"
    TEXT = "text"


class TokenKind(StrEnum):
    SYMBOL = "symbol"
    KEY = "key"
    STRING = "string"
    NUMBER = "number"
    CONSTANT = "constant"
    COMMENT = "comment"
    # a `{{ ... }}` or `{% ... %}` of a string, with its delimiters
    TEMPLATE = "template"
    # a string that is a color, like "#ff8800" (with its quotes)
    COLOR = "color"
    # a placeholder openHASP replaces at runtime, like `%ip%` (without the quotes of its string, see `placeholders.py`)
    PLACEHOLDER = "placeholder"
    COMMAND = "command"
    ARGUMENT = "argument"


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    kind: TokenKind

    def text(self, line: str) -> str:
        return line[self.start : self.end]


_LANGUAGES = {
    ".jsonl": Language.JSONL,
    ".json": Language.JSON,
    ".cmd": Language.CMD,
    ".yaml": Language.YAML,
    ".yml": Language.YAML,
}

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_CONSTANT = re.compile(r"true|false|null")
_COLOR = re.compile(r"([\"'])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\1")
_YAML_KEY = re.compile(r"(\s*(?:-\s+)?)([^\s:#'\"][^:#]*?)(\s*:)(?=\s|$)")
_SYMBOLS = "{}[],:"


def language_of(path: Path) -> Language:
    return _LANGUAGES.get(path.suffix.lower(), Language.TEXT)


def tokenize_line(line: str, language: Language) -> List[Token]:
    """:return: the highlighted parts of a line, in order. Text between them has no kind."""
    if language in (Language.JSONL, Language.JSON):
        # a placeholder is only replaced in the objects of a page, not in a JSON file like `config.json`
        return _tokenize_jsonl(line, placeholders=language == Language.JSONL)
    if language == Language.CMD:
        return _tokenize_cmd(line)
    if language == Language.YAML:
        return _tokenize_yaml(line)
    return []


def find_templates(text: str, offset: int = 0) -> List[Token]:
    """:return: the templates in a text (see `template_spans`), shifted by `offset`"""
    return [Token(offset + start, offset + end, TokenKind.TEMPLATE) for start, end in template_spans(text)]


def _tokenize_jsonl(line: str, placeholders: bool) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    while i < len(line):
        char = line[i]
        if char.isspace():
            i += 1
        elif line.startswith("//", i):
            tokens.append(Token(i, len(line), TokenKind.COMMENT))
            break
        elif char == '"':
            end = _end_of_string(line, i)
            if placeholders and _is_placeholder(line, i, end, tokens):
                tokens += [Token(i, i + 1, TokenKind.STRING), Token(i + 1, end - 1, TokenKind.PLACEHOLDER)]
                tokens.append(Token(end - 1, end, TokenKind.STRING))
            else:
                tokens += _string_tokens(line, i, end)
            i = end
        elif char in _SYMBOLS:
            tokens.append(Token(i, i + 1, TokenKind.SYMBOL))
            i += 1
        elif match := (_NUMBER.match(line, i) or _CONSTANT.match(line, i)):
            kind = TokenKind.NUMBER if match.group()[0] in "-0123456789" else TokenKind.CONSTANT
            tokens.append(Token(i, match.end(), kind))
            i = match.end()
        else:
            i += 1
    return tokens


def _end_of_string(line: str, start: int) -> int:
    """:return: the index after the closing quote, the end of the line if there is none"""
    i = start + 1
    while i < len(line):
        if line[i] == "\\":
            i += 2
        elif line[i] == '"':
            return i + 1
        else:
            i += 1
    return len(line)


def _is_placeholder(line: str, start: int, end: int, tokens: List[Token]) -> bool:
    """
    :param tokens: the tokens of the line before the string
    :return: whether the string from `start` to `end` is the value of a `text` and a placeholder, which openHASP replaces only when
        it is the whole text (see `placeholders.py`)
    """
    if end - start < 2 or line[end - 1] != '"' or len(tokens) < 2:
        return False
    key, colon = tokens[-2:]
    if key.kind != TokenKind.KEY or key.text(line) != f'"{PLACEHOLDER_PROPERTY}"' or colon.text(line) != ":":
        return False
    return line[end:].lstrip()[:1] != ":" and placeholder_of(line[start + 1 : end - 1]) is not None


def _string_tokens(line: str, start: int, end: int) -> List[Token]:
    """A string is a key if a `:` follows, a color if it looks like one; the templates in it are tokens of their own."""
    rest = line[end:].lstrip()
    kind = TokenKind.KEY if rest.startswith(":") else TokenKind.STRING
    if kind == TokenKind.STRING and _COLOR.fullmatch(line[start:end]):
        return [Token(start, end, TokenKind.COLOR)]
    return _split_around_templates(line, start, end, kind)


def _split_around_templates(line: str, start: int, end: int, kind: TokenKind) -> List[Token]:
    result = []
    position = start
    for template in find_templates(line[start:end], start):
        if template.start > position:
            result.append(Token(position, template.start, kind))
        result.append(template)
        position = template.end
    if position < end:
        result.append(Token(position, end, kind))
    return result


def _tokenize_cmd(line: str) -> List[Token]:
    stripped = line.lstrip()
    if not stripped:
        return []
    indent = len(line) - len(stripped)
    command_end = indent + len(stripped.split(maxsplit=1)[0])
    tokens = _split_around_templates(line, indent, command_end, TokenKind.COMMAND)
    if command_end < len(line):
        tokens += _split_around_templates(line, command_end, len(line), TokenKind.ARGUMENT)
    return [token for token in tokens if token.text(line).strip()]


def _tokenize_yaml(line: str) -> List[Token]:
    tokens: List[Token] = []
    comment = _yaml_comment_start(line)
    code = line if comment is None else line[:comment]
    value_start = 0
    if match := _YAML_KEY.match(code):
        tokens.append(Token(match.start(2), match.end(2), TokenKind.KEY))
        value_start = match.end(3)
    value = code[value_start:]
    stripped = value.strip()
    if stripped:
        offset = value_start + len(value) - len(value.lstrip())
        end = value_start + len(value.rstrip())
        if _NUMBER.fullmatch(stripped):
            tokens.append(Token(offset, end, TokenKind.NUMBER))
        elif _CONSTANT.fullmatch(stripped):
            tokens.append(Token(offset, end, TokenKind.CONSTANT))
        elif _COLOR.fullmatch(stripped):
            tokens.append(Token(offset, end, TokenKind.COLOR))
        else:
            tokens += _split_around_templates(line, offset, end, TokenKind.STRING)
    if comment is not None:
        tokens.append(Token(comment, len(line), TokenKind.COMMENT))
    return tokens


def _yaml_comment_start(line: str) -> Optional[int]:
    """:return: where the comment of a line starts: a `#` at the start or after a space, outside of quotes"""
    quote = None
    for i, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (i == 0 or line[i - 1].isspace()):
            return i
    return None
