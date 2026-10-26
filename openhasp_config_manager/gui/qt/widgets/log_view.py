from typing import Dict, Iterable, Optional

from PyQt6 import QtCore
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget

from openhasp_config_manager.gui.domain.log_history import MAX_ENTRIES, LogHistory, LogLinkState, describe_link, matches
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.theme import current_colors
from openhasp_config_manager.openhasp_client.logs import LogEntry, LogLevel, Segment

# if the view is scrolled to this many pixels from the end it follows the new entries
_FOLLOW_TOLERANCE = 4


class LogView(QWidget):
    """
    The log of a plate as colored text that follows the newest entry, like a terminal, unless it was scrolled up to read.
    Shows what it is given: the connection is the business of `LogStreamController`.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._history = LogHistory()
        self._query = ""

        layout = UiComponents.create_column(parent=self)
        header = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._status = UiComponents.create_label("", role="hint")
        header.addWidget(self._status, 1)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter…")
        self._filter.setClearButtonEnabled(True)
        self._filter.setMaximumWidth(260)
        self._filter.textChanged.connect(self._on_filter_changed)
        header.addWidget(self._filter)
        self._clear_button = UiComponents.create_button(
            title="", icon="delete-sweep", tooltip="Clear the log (the plate keeps no history)", on_click=self.clear
        )
        header.addWidget(self._clear_button)
        layout.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMaximumBlockCount(MAX_ENTRIES)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self._text, 1)

        self.set_link(LogLinkState.NO_DEVICE)

    # --- content ---

    def add_entries(self, entries: Iterable[LogEntry]):
        entries = list(entries)
        self._history.add(entries)
        shown = [entry for entry in entries if matches(entry, self._query)]
        if shown:
            follow = self._is_following()
            self._insert(shown)
            if follow:
                self._scroll_to_end()

    def clear(self):
        self._history.clear()
        self._text.clear()

    def set_link(self, state: LogLinkState, error: Optional[str] = None):
        text, role = describe_link(state, error)
        self._status.setText(text)
        self._status.setToolTip(error or "")
        self._status.setProperty("role", role)
        # the style sheet only looks at a changed property after the widget was polished again
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def text(self) -> str:
        """:return: the text that is shown"""
        return self._text.toPlainText()

    def refresh_theme(self):
        self._render()

    # --- internals ---

    def _on_filter_changed(self, text: str):
        self._query = text.strip()
        self._render()

    def _render(self):
        follow = self._is_following()
        self._text.clear()
        self._insert(self._history.filtered(self._query))
        if follow:
            self._scroll_to_end()

    def _insert(self, entries: Iterable[LogEntry]):
        formats = self._formats()
        cursor = QTextCursor(self._text.document())
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for entry in entries:
            if not self._text.document().isEmpty():
                cursor.insertBlock()
            for segment, text in entry.segments():
                cursor.insertText(text, formats.segment_format(segment, entry.level))
        cursor.endEditBlock()

    def _is_following(self) -> bool:
        bar = self._text.verticalScrollBar()
        return bar.value() >= bar.maximum() - _FOLLOW_TOLERANCE

    def _scroll_to_end(self):
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _formats(self) -> "_Formats":
        return _Formats(self.palette())


class _Formats:
    """The character formats of the parts and levels of an entry, for the colors of the current theme."""

    def __init__(self, palette: QPalette):
        colors = current_colors()
        muted = palette.color(QPalette.ColorRole.PlaceholderText)
        self._level_colors: Dict[Optional[LogLevel], QColor] = {
            LogLevel.ERROR: QColor(colors.error),
            LogLevel.WARNING: QColor(colors.warning),
            LogLevel.TRACE: muted,
            LogLevel.VERBOSE: QColor(colors.log_verbose),
            LogLevel.DEBUG: QColor(colors.log_debug),
            LogLevel.SENT: QColor(colors.success),
            LogLevel.RECEIVED: QColor(colors.log_received),
        }
        self._muted = muted

    def segment_format(self, segment: Segment, level: Optional[LogLevel]) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if segment in (Segment.TIMESTAMP, Segment.MEMORY):
            fmt.setForeground(self._muted)
        elif segment == Segment.TAG:
            fmt.setFontWeight(QFont.Weight.Bold)
        elif level in self._level_colors:
            fmt.setForeground(self._level_colors[level])
        return fmt
