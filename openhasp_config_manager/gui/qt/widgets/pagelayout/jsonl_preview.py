import re
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtWidgets import QSizePolicy, QTextEdit
from orjson import orjson

from openhasp_config_manager.gui.qt.theme import current_mode, ThemeMode

# syntax colors: (dark theme, light theme)
_SYNTAX_COLORS = {
    "symbol": ("#FFD700", "#795E26"),
    "key": ("#9CDCFE", "#0451A5"),
    "string": ("#CE9178", "#A31515"),
    "number": ("#B5CEA8", "#098658"),
    "constant": ("#569CD6", "#0000FF"),
}


def _syntax_color(name: str) -> QColor:
    dark, light = _SYNTAX_COLORS[name]
    return QColor(dark if current_mode() == ThemeMode.DARK else light)


class PageJsonlPreviewWidget(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Roboto Mono", 10))
        self.setPlaceholderText("No objects on this page.")

        self.highlighter = JsonLHighlighter(self.document())

        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(size_policy)

    def refresh_theme(self):
        self.highlighter.setDocument(None)
        self.highlighter = JsonLHighlighter(self.document())

    def set_objects(self, page_objects: List[dict]):
        """
        Set the objects for the page.
        :param page_objects: the list of objects to set
        """
        sorted_page_objects = sorted(
            page_objects,
            key=lambda obj: (
                obj.get("page", 0),
                obj.get("id", 0),
                obj.get("y", ""),
                obj.get("x", ""),
            ),
        )

        content = "\n".join(map(lambda x: orjson.dumps(x).decode(), sorted_page_objects))
        self.setText(content)


class JsonLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._format_cache = {}
        self.rules = []

        # --- Standard Syntax Rules ---

        # 1. Braces and Brackets {} []
        symbol_format = QTextCharFormat()
        symbol_format.setForeground(_syntax_color("symbol"))
        self.rules.append((re.compile(r"[\{\}\[\]]"), symbol_format))

        # 2. Keys (The property names)
        key_format = QTextCharFormat()
        key_format.setForeground(_syntax_color("key"))
        self.rules.append((re.compile(r'"[^"\\]*"(?=\s*:)'), key_format))

        # 3. Standard Strings (Non-color values)
        # Uses a negative lookahead to avoid matching hex codes
        string_format = QTextCharFormat()
        string_format.setForeground(_syntax_color("string"))
        self.rules.append((re.compile(r'(?<=:)\s*"(?!#)[^"\\]*"'), string_format))

        # 4. Numbers (int/float)
        number_format = QTextCharFormat()
        number_format.setForeground(_syntax_color("number"))
        self.rules.append((re.compile(r"\b-?\d+(?:\.\d+)?\b"), number_format))

        # 5. Booleans and Null
        const_format = QTextCharFormat()
        const_format.setForeground(_syntax_color("constant"))
        self.rules.append((re.compile(r"\b(true|false|null)\b"), const_format))

        # --- Dynamic Color Rule ---

        # Matches "#FFFFFF" or "#FFF" (3 or 6 hex digits)
        self.color_regex = re.compile(r'"#([0-9a-fA-F]{3,6})"')

    def get_color_format(self, hex_val: str) -> QTextCharFormat:
        """Creates or retrieves a format with a colored background."""
        if hex_val not in self._format_cache:
            color = QColor(f"#{hex_val}")
            fmt = QTextCharFormat()
            fmt.setBackground(color)

            # Use W3C relative luminance formula or simple lightness to
            # determine if text should be black or white for readability.
            if color.lightness() > 150:
                fmt.setForeground(Qt.GlobalColor.black)
            else:
                fmt.setForeground(Qt.GlobalColor.white)

            # Make the hex code stand out a bit more
            fmt.setFontWeight(QFont.Weight.Bold)
            self._format_cache[hex_val] = fmt

        return self._format_cache[hex_val]

    def highlightBlock(self, text: str):
        # Apply standard syntax rules
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        # Apply dynamic color background rules
        for match in self.color_regex.finditer(text):
            hex_val = match.group(1)
            # OpenHASP colors are usually 6 digits, but we support 3
            if len(hex_val) in (3, 6):
                fmt = self.get_color_format(hex_val)
                self.setFormat(match.start(), match.end() - match.start(), fmt)
