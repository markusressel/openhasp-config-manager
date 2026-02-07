import re
from typing import List

from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtWidgets import QSizePolicy, QTextEdit
from orjson import orjson

from openhasp_config_manager.ui.qt.pagelayout import OpenHaspDevicePagesData


class PageJsonlPreviewWidget(QTextEdit):
    def __init__(self, page: OpenHaspDevicePagesData, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Roboto Mono", 10))

        self.highlighter = JsonLHighlighter(self.document())

        self.set_page(page)

        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(size_policy)

    def set_page(self, page: OpenHaspDevicePagesData):
        self.page = page
        self.setText(page.jsonl_components[0].content)

    def set_objects(self, page_objects: List[dict]):
        """
        Set the objects for the page.
        :param page_objects: the list of objects to set
        """
        sorted_page_objects = sorted(page_objects, key=lambda obj: (
            obj.get("page", 0), obj.get("id", 0), obj.get("y", ""), obj.get("x", "")))

        content = "\n".join(map(lambda x: orjson.dumps(x).decode(), sorted_page_objects))
        self.setText(content)

class JsonLHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # 1. Braces and Brackets {} []
        symbol_format = QTextCharFormat()
        symbol_format.setForeground(QColor("#FFD700"))  # Gold
        self.rules.append((re.compile(r"[\{\}\[\]]"), symbol_format))

        # 2. Keys (The property names)
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#9CDCFE"))  # Light Blue
        self.rules.append((re.compile(r'"[^"\\]*"(?=\s*:)'), key_format))

        # 3. Hex Color Codes (Inside strings, e.g., "#558B2F")
        color_code_format = QTextCharFormat()
        color_code_format.setForeground(QColor("#CE9178"))  # Salmon/Orange
        color_code_format.setFontItalic(True)
        # Match # followed by 6 hex chars inside quotes
        self.rules.append((re.compile(r'"#(?:[0-9a-fA-F]{3}){1,2}"'), color_code_format))

        # 4. Standard Strings (Values that aren't colors)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))  # Salmon
        # This matches strings after a colon, excluding the hex pattern above
        self.rules.append((re.compile(r'(?<=:)\s*"(?!#)[^"\\]*"'), string_format))

        # 5. Numbers (int/float)
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # Sage Green
        self.rules.append((re.compile(r"\b-?\d+(?:\.\d+)?\b"), number_format))

        # 6. Booleans and Null
        const_format = QTextCharFormat()
        const_format.setForeground(QColor("#569CD6"))  # Blue
        self.rules.append((re.compile(r"\b(true|false|null)\b"), const_format))

        # 7. The Colon (Separator)
        separator_format = QTextCharFormat()
        separator_format.setForeground(QColor("#FFFFFF"))
        self.rules.append((re.compile(r":"), separator_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)