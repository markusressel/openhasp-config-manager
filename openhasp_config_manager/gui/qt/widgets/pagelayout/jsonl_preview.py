from typing import Callable, Dict, List, Set

from PyQt6.QtGui import QFont, QPalette, QTextCharFormat, QTextCursor, QTextFormat
from PyQt6.QtWidgets import QSizePolicy, QTextEdit
from orjson import orjson

from openhasp_config_manager.gui.domain.problems import geometry_value, number_or
from openhasp_config_manager.gui.domain.source_syntax import Language
from openhasp_config_manager.gui.qt.source_highlighter import SourceHighlighter

# the opacity of dimmed lines, 0..255
DIMMED_ALPHA = 80
# the opacity of the background of the lines of the selected objects, 0..255
SELECTED_ALPHA = 70


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
        # the lines of the dimmed objects, decided when the objects or the predicate change: a selection changes nothing about it,
        # and the objects can be gone from the draft by then (removed, the page is rebuilt after the selection changed)
        self._dimmed_lines: Set[int] = set()
        # the objects selected in the preview, their lines are highlighted
        self._selected: List[dict] = []

        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(size_policy)

    def refresh_theme(self):
        self.highlighter.setDocument(None)
        self.highlighter = SourceHighlighter(self.document(), Language.JSONL)
        self._update_selections()

    def set_dimmed_predicate(self, is_dimmed: Callable[[Dict], bool]):
        """Dim the lines of the objects for which the predicate is true."""
        self._is_dimmed = is_dimmed
        self._update_dimmed_lines()
        self._update_selections()

    def set_selected_objects(self, objects: List[dict]):
        """Highlight the lines of the objects selected in the preview, and scroll to the first of them."""
        self._selected = list(objects)
        self._update_selections()
        lines = self.selected_lines
        if lines:
            self.setTextCursor(QTextCursor(self.document().findBlockByNumber(lines[0])))
            self.ensureCursorVisible()

    @property
    def selected_lines(self) -> List[int]:
        """:return: the lines (starting at 0) of the selected objects that are on the page"""
        return [index for index, obj in enumerate(self._objects) if any(obj is selected for selected in self._selected)]

    def _update_dimmed_lines(self):
        self._dimmed_lines = {index for index, obj in enumerate(self._objects) if self._is_dimmed(obj)}

    def _update_selections(self):
        dimmed_color = self.palette().color(self.foregroundRole())
        dimmed_color.setAlpha(DIMMED_ALPHA)
        dimmed = QTextCharFormat()
        dimmed.setForeground(dimmed_color)
        selected_color = self.palette().color(QPalette.ColorRole.Highlight)
        selected_color.setAlpha(SELECTED_ALPHA)
        selected = QTextCharFormat()
        selected.setBackground(selected_color)
        selected.setProperty(QTextFormat.Property.FullWidthSelection, True)

        selections = []
        selected_lines = set(self.selected_lines)
        for index in range(len(self._objects)):
            if index in selected_lines:
                selections.append(self._line_selection(index, selected))
            if index in self._dimmed_lines:
                selections.append(self._line_selection(index, dimmed))
        self.setExtraSelections(selections)

    def _line_selection(self, index: int, fmt: QTextCharFormat) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(self.document().findBlockByNumber(index))
        selection.cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        selection.format = fmt
        return selection

    def set_objects(self, page_objects: List[dict]):
        """
        Set the objects for the page.
        :param page_objects: the list of objects to set
        """
        sorted_page_objects = sorted(
            page_objects,
            # values that are not numbers (templates that can't be rendered) sort like 0, they can't be compared with numbers
            key=lambda obj: (
                number_or(obj.get("page"), 0),
                number_or(obj.get("id"), 0),
                geometry_value(obj, "y"),
                geometry_value(obj, "x"),
            ),
        )

        self._objects = sorted_page_objects
        content = "\n".join(map(lambda x: orjson.dumps(x).decode(), sorted_page_objects))
        self.setText(content)
        self._update_dimmed_lines()
        self._update_selections()
