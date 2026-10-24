from typing import Callable, Dict, List

from PyQt6.QtGui import QTextCharFormat, QFont, QTextCursor
from PyQt6.QtWidgets import QSizePolicy, QTextEdit
from orjson import orjson

from openhasp_config_manager.gui.domain.source_syntax import Language
from openhasp_config_manager.gui.qt.source_highlighter import SourceHighlighter

# the opacity of dimmed lines, 0..255
DIMMED_ALPHA = 80


class PageJsonlPreviewWidget(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Roboto Mono", 10))
        self.setPlaceholderText("No objects on this page.")

        self.highlighter = SourceHighlighter(self.document(), Language.JSONL)
        # the objects in the order of the lines, and which of them are dimmed (e.g. those of other files)
        self._objects: List[dict] = []
        self._is_dimmed: Callable[[Dict], bool] = lambda _obj: False

        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(size_policy)

    def refresh_theme(self):
        self.highlighter.setDocument(None)
        self.highlighter = SourceHighlighter(self.document(), Language.JSONL)
        self._update_dimming()

    def set_dimmed_predicate(self, is_dimmed: Callable[[Dict], bool]):
        """Dim the lines of the objects for which the predicate is true."""
        self._is_dimmed = is_dimmed
        self._update_dimming()

    def _update_dimming(self):
        color = self.palette().color(self.foregroundRole())
        color.setAlpha(DIMMED_ALPHA)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        selections = []
        for index, obj in enumerate(self._objects):
            if self._is_dimmed(obj):
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(self.document().findBlockByNumber(index))
                selection.cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                selection.format = fmt
                selections.append(selection)
        self.setExtraSelections(selections)

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
                obj.get("y", 0),
                obj.get("x", 0),
            ),
        )

        self._objects = sorted_page_objects
        content = "\n".join(map(lambda x: orjson.dumps(x).decode(), sorted_page_objects))
        self.setText(content)
        self._update_dimming()
