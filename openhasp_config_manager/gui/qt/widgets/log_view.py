from typing import Dict, Iterable, Optional

from PyQt6 import QtCore
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QToolButton, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.log_history import MAX_ENTRIES, LogHistory, LogLinkState, describe_link, matches
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.theme import current_colors
from openhasp_config_manager.openhasp_client.logs import LogEntry, LogLevel, Segment

# if the view is scrolled to this many pixels from the end it follows the new entries
_FOLLOW_TOLERANCE = 4
_FOLLOW_BUTTON_MARGIN = 12


class LogView(QWidget):
    """
    The log of a plate as colored text that follows the newest entry, like a terminal, unless it was scrolled up to read.
    Shows what it is given: the connection is the business of `LogStreamController`.
    """

    # the user wants the plate to send the colors of the levels, see `set_colors_missing`
    enableColorsRequested = QtCore.pyqtSignal()

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

        # shown while the plate sends no colors, so the levels are only guessed
        self._colors_hint = QFrame()
        hint_row = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        hint_row.setContentsMargins(0, 0, 0, 0)
        self._colors_hint.setLayout(hint_row)
        hint_row.addWidget(
            UiComponents.create_label(
                "The plate sends no colors, so errors and warnings are only guessed from the text.",
                role="hint",
                word_wrap=True,
            ),
            1,
        )
        hint_row.addWidget(
            UiComponents.create_button(
                title="Enable colors…",
                icon="palette",
                tooltip="Ask the plate to send the level of each line (debug.ansi)",
                on_click=self.enableColorsRequested.emit,
            )
        )
        self._colors_hint.hide()
        layout.addWidget(self._colors_hint)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMaximumBlockCount(MAX_ENTRIES)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self._text, 1)

        # floats over the end of the log while it was scrolled up, to follow the newest entry again
        self._follow_bar = QFrame(self._text)
        self._follow_bar.setProperty("role", "floating")
        QHBoxLayout(self._follow_bar).setContentsMargins(
            UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half
        )
        self._follow_button = QToolButton()
        self._follow_bar.layout().addWidget(self._follow_button)
        self._follow_button.setText("Follow")
        self._follow_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._follow_button.setToolTip("Scroll to the newest entry and follow the log again")
        ThemedIcons.apply(self._follow_button, "arrow-collapse-down")
        self._follow_button.clicked.connect(self.follow)
        self._follow_bar.hide()
        self._text.verticalScrollBar().valueChanged.connect(lambda _: self._update_follow_button())
        self._text.installEventFilter(self)

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
            self._update_follow_button()

    def clear(self):
        self._history.clear()
        self._text.clear()
        self._update_follow_button()

    def follow(self):
        """Scrolls to the newest entry. The view follows the new ones from then on."""
        self._scroll_to_end()
        self._update_follow_button()

    def set_colors_missing(self, missing: bool):
        self._colors_hint.setVisible(missing)

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

    def is_follow_button_visible(self) -> bool:
        return not self._follow_bar.isHidden()

    def _update_follow_button(self):
        self._follow_bar.setVisible(not self._is_following())
        self._place_follow_button()

    def _place_follow_button(self):
        viewport = self._text.viewport().geometry()
        bar = self._follow_bar
        bar.adjustSize()
        bar.move(
            viewport.right() - bar.width() - _FOLLOW_BUTTON_MARGIN,
            viewport.bottom() - bar.height() - _FOLLOW_BUTTON_MARGIN,
        )
        bar.raise_()

    def eventFilter(self, watched, event):
        if watched is self._text and event.type() == QtCore.QEvent.Type.Resize:
            QtCore.QTimer.singleShot(0, self._update_follow_button)
        return super().eventFilter(watched, event)

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
