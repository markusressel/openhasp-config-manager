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

        self.highlighter = JsonHighlighter(self.document())

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


class JsonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # Key format (e.g., "id":)
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#ce9178"))  # Terracotta
        key_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((re.compile(r'"[^"\\]*"(?=\s*:)'), key_format))

        # String value format
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#9cdcfe"))  # Light Blue
        self.rules.append((re.compile(r'(?<=:)\s*"[^"\\]*"'), string_format))

        # Number format
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))  # Light Green
        self.rules.append((re.compile(r'\b\d+(\.\d+)?\b'), number_format))

        # Boolean/Null format
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))  # Azure
        self.rules.append((re.compile(r'\b(true|false|null)\b'), keyword_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
