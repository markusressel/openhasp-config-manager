from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from openhasp_config_manager.gui.domain.source.syntax import JsonlState, Language, TokenKind, tokenize_jsonl, tokenize_line
from openhasp_config_manager.gui.qt.theme import ThemeMode, current_mode

# syntax colors: (dark theme, light theme)
_SYNTAX_COLORS = {
    TokenKind.SYMBOL: ("#FFD700", "#795E26"),
    TokenKind.KEY: ("#9CDCFE", "#0451A5"),
    TokenKind.STRING: ("#CE9178", "#A31515"),
    TokenKind.NUMBER: ("#B5CEA8", "#098658"),
    TokenKind.CONSTANT: ("#569CD6", "#0000FF"),
    TokenKind.COMMENT: ("#6A9955", "#008000"),
    TokenKind.TEMPLATE: ("#C586C0", "#AF00DB"),
    TokenKind.COMMAND: ("#569CD6", "#0000FF"),
    TokenKind.ARGUMENT: ("#CE9178", "#A31515"),
    TokenKind.DIRECTIVE: ("#4EC9B0", "#267F99"),
}


def syntax_color(kind: TokenKind) -> QColor:
    dark, light = _SYNTAX_COLORS[kind]
    return QColor(dark if current_mode() == ThemeMode.DARK else light)


class SourceHighlighter(QSyntaxHighlighter):
    """Colors the lines of a document by what `source_syntax.tokenize_line` finds in them."""

    def __init__(self, document, language: Language):
        super().__init__(document)
        self._language = language
        self._formats: Dict[TokenKind, QTextCharFormat] = {}
        for kind in _SYNTAX_COLORS:
            fmt = QTextCharFormat()
            fmt.setForeground(syntax_color(kind))
            if kind == TokenKind.COMMENT:
                fmt.setFontItalic(True)
            if kind == TokenKind.TEMPLATE:
                fmt.setFontWeight(QFont.Weight.DemiBold)
            self._formats[kind] = fmt
        self._color_formats: Dict[str, QTextCharFormat] = {}

    def highlightBlock(self, text: str):
        for token in self._tokens(text):
            if token.kind == TokenKind.COLOR:
                self.setFormat(token.start, token.end - token.start, self._color_format(token.text(text)[2:-1]))
            else:
                self.setFormat(token.start, token.end - token.start, self._formats[token.kind])

    def _tokens(self, text: str):
        if self._language != Language.JSONL:
            return tokenize_line(text, self._language)
        # the state of a block says where the next line starts: in a directive object or not (see `tokenize_jsonl`)
        previous = self.previousBlockState()
        state = JsonlState() if previous < 0 else JsonlState(previous // 2, bool(previous % 2))
        tokens, after = tokenize_jsonl(text, state)
        self.setCurrentBlockState(after.depth * 2 + int(after.directive))
        return tokens

    def _color_format(self, hex_value: str) -> QTextCharFormat:
        """The color of a color string as the background of the string, with a readable text color."""
        if hex_value not in self._color_formats:
            color = QColor(f"#{hex_value}")
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            fmt.setForeground(Qt.GlobalColor.black if color.lightness() > 150 else Qt.GlobalColor.white)
            fmt.setFontWeight(QFont.Weight.Bold)
            self._color_formats[hex_value] = fmt
        return self._color_formats[hex_value]
