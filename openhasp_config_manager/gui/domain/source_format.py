"""Formatting a whole text: indentation by the depth of the brackets, no spaces at the end of lines. Qt-free."""

from typing import List

from openhasp_config_manager.gui.domain.source_edit import INDENT
from openhasp_config_manager.gui.domain.source_syntax import Language, TokenKind, tokenize_line

_OPENING = "{["
_CLOSING = "}]"


def format_text(text: str, language: Language) -> str:
    """
    :return: the text with the lines indented by the depth of the brackets (JSONL), no spaces at the end of the lines and one
        line break at the end. The contents of the lines, comments and blank lines stay as they are. Other languages only get
        the clean line ends.
    """
    lines = text.split("\n")
    if language == Language.JSONL:
        lines = _indent_by_depth(lines)
    else:
        lines = [line.rstrip() for line in lines]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _indent_by_depth(lines: List[str]) -> List[str]:
    result = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        tokens = tokenize_line(stripped, Language.JSONL)
        symbols = [stripped[token.start] for token in tokens if token.kind == TokenKind.SYMBOL]
        starts_with_closing = bool(tokens) and tokens[0].kind == TokenKind.SYMBOL and stripped[0] in _CLOSING
        indent = max(depth - (1 if starts_with_closing else 0), 0)
        result.append(INDENT * indent + stripped if stripped else "")
        depth = max(depth + sum(symbol in _OPENING for symbol in symbols) - sum(symbol in _CLOSING for symbol in symbols), 0)
    return result
