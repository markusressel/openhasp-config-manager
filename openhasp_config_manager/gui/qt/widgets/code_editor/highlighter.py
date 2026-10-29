from typing import Dict, Iterator

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextBlock, QTextCharFormat

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
    TokenKind.PLACEHOLDER: ("#4EC9B0", "#267F99"),
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
        # connected after `QSyntaxHighlighter` itself, so the changed lines are highlighted already
        document.contentsChange.connect(self._on_contents_change)

    def setDocument(self, document):
        # only for a change of the document after `__init__` (Qt's constructor doesn't call this override)
        if self.document() is not None:
            self.document().contentsChange.disconnect(self._on_contents_change)
        super().setDocument(document)
        if document is not None:
            document.contentsChange.connect(self._on_contents_change)

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
        block = self.currentBlock()
        tokens, after = tokenize_jsonl(text, _jsonl_state(self.previousBlockState()), following=lambda: _texts_after(block))
        self.setCurrentBlockState(_block_state(after))
        return tokens

    def _on_contents_change(self, position: int, removed: int, added: int):
        """
        Highlights the first line of the object of a change again when the change made it a directive object or a plain one:
        Qt only highlights the changed lines and the ones after them, but its `"vars"` may be above the `"!include"`.
        """
        if self._language != Language.JSONL:
            return
        changed = self.document().findBlock(position)
        block = changed
        while block.previous().isValid() and _jsonl_state(block.previous().userState()).depth > 0:
            block = block.previous()
        if block == changed:
            # Qt highlights the changed line itself, with all lines of its object
            return
        before = _jsonl_state(block.previous().userState())
        _, after = tokenize_jsonl(block.text(), before, following=lambda: _texts_after(block))
        if _block_state(after) != block.userState():
            self.rehighlightBlock(block)

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


def _jsonl_state(block_state: int) -> JsonlState:
    return JsonlState() if block_state < 0 else JsonlState(block_state // 2, bool(block_state % 2))


def _block_state(state: JsonlState) -> int:
    return state.depth * 2 + int(state.directive)


def _texts_after(block: QTextBlock) -> Iterator[str]:
    block = block.next()
    while block.isValid():
        yield block.text()
        block = block.next()
