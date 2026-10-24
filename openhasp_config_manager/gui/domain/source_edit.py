"""Edits of the text of a file that depend on its syntax: comments, indentation, matching brackets. Qt-free."""

from typing import List, Optional

from openhasp_config_manager.gui.domain.source_syntax import Language, TokenKind, tokenize_line

INDENT = "  "

_COMMENT_PREFIXES = {Language.JSONL: "//", Language.YAML: "#"}
_PAIRS = {"{": "}", "[": "]"}
_CLOSING = {closing: opening for opening, closing in _PAIRS.items()}


def toggle_comment(lines: List[str], language: Language) -> List[str]:
    """
    Comment the lines out, or remove the comment if all of them are commented. Empty lines stay as they are.
    :return: the new lines (the same ones for languages that have no comments)
    """
    prefix = _COMMENT_PREFIXES.get(language)
    filled = [line for line in lines if line.strip()]
    if prefix is None or not filled:
        return list(lines)
    if all(line.lstrip().startswith(prefix) for line in filled):
        return [_uncomment(line, prefix) for line in lines]
    column = min(len(line) - len(line.lstrip()) for line in filled)
    return [line if not line.strip() else f"{line[:column]}{prefix} {line[column:]}" for line in lines]


def _uncomment(line: str, prefix: str) -> str:
    if not line.strip():
        return line
    indent = len(line) - len(line.lstrip())
    rest = line[indent + len(prefix) :]
    return line[:indent] + (rest[1:] if rest.startswith(" ") else rest)


def indent_for_new_line(line_before_cursor: str, language: Language) -> str:
    """:return: the indentation of the line that follows a line: the same, and one level more after an opening bracket"""
    indent = line_before_cursor[: len(line_before_cursor) - len(line_before_cursor.lstrip())]
    code = line_before_cursor.rstrip()
    opens = code.endswith(("{", "[")) or (language == Language.YAML and code.endswith(":"))
    return indent + INDENT if opens else indent


def matching_bracket(text: str, position: int, language: Language = Language.JSONL) -> Optional[int]:
    """
    :param position: the index of a bracket in the text
    :return: the index of the bracket it pairs with, None if it is not a bracket, or has no partner. Brackets in strings and
        comments are not brackets.
    """
    brackets = _brackets(text, language)
    if position not in brackets:
        return None
    char = brackets[position]
    forward = char in _PAIRS
    partner = _PAIRS[char] if forward else _CLOSING[char]
    candidates = sorted(
        (index for index in brackets if (index > position) == forward and index != position), reverse=not forward
    )
    depth = 0
    for index in candidates:
        if brackets[index] == char:
            depth += 1
        elif brackets[index] == partner:
            if depth == 0:
                return index
            depth -= 1
    return None


def _brackets(text: str, language: Language) -> dict:
    result = {}
    offset = 0
    for line in text.split("\n"):
        for token in tokenize_line(line, language):
            if token.kind == TokenKind.SYMBOL and line[token.start] in "{}[]":
                result[offset + token.start] = line[token.start]
        offset += len(line) + 1
    return result
