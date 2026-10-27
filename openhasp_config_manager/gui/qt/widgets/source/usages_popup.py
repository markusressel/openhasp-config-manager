import html
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QFontDatabase, QPalette
from PyQt6.QtWidgets import QFrame, QLabel, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, language_of, tokenize_line
from openhasp_config_manager.gui.domain.variables.usage_preview import UsagePreview, group_by_file, preview_of
from openhasp_config_manager.gui.domain.variables.usages import Usage
from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color

# the lines of code shown before and after the usage in the preview
_CONTEXT_LINES = 6
# the characters of a line that are shown in the preview; the rest is cut off, around the usage
_LINE_WIDTH = 160
_BEFORE_USAGE = 50
# the characters of the line of a usage in the list
_LIST_WIDTH = 100
_WIDTH = 820
# the contrast of text on the mark of the usage (WCAG: 4.5 for normal text, 3 for large text)
_MIN_CONTRAST = 4.5
_MARK_STRENGTH = 0.35
_SELECTION_STRENGTH = 0.2
_HEIGHT = 520
_MAX_SCREEN_SHARE = 0.7

_USAGE_ROLE = Qt.ItemDataRole.UserRole


def _blend(color: QColor, over: QColor, alpha: float) -> QColor:
    return QColor(
        round(color.red() * alpha + over.red() * (1 - alpha)),
        round(color.green() * alpha + over.green() * (1 - alpha)),
        round(color.blue() * alpha + over.blue() * (1 - alpha)),
    )


def _luminance(color: QColor) -> float:
    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(color.red()) + 0.7152 * linear(color.green()) + 0.0722 * linear(color.blue())


def _contrast(first: QColor, second: QColor) -> float:
    """:return: the WCAG contrast ratio of two colors, from 1 to 21"""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _readable_on(color: QColor, background: QColor, text: QColor) -> QColor:
    """:return: the color if it can be read on the background, else the text color, else black or white"""
    for candidate in (color, text):
        if _contrast(candidate, background) >= _MIN_CONTRAST:
            return candidate
    return max((QColor("black"), QColor("white")), key=lambda option: _contrast(option, background))


def _span(text: str, color: str, background: str = "", bold: bool = False) -> str:
    style = f"color:{color};"
    if background:
        style += f"background-color:{background};"
    if bold:
        style += "font-weight:bold;"
    return f'<span style="{style}">{html.escape(text)}</span>'


def _line_html(
    line: str,
    language: Language,
    palette: QPalette,
    mark: Optional[Tuple[int, int]],
    start: int = 0,
    end: Optional[int] = None,
) -> str:
    """
    :param mark: where in the line the usage is (column, length)
    :param start: where the shown part of the line starts
    :param end: where the shown part of the line ends
    :return: a part of a line as syntax highlighted HTML, with the usage marked
    """
    end = len(line) if end is None else end
    muted = palette.color(QPalette.ColorRole.PlaceholderText).name()
    mark_background = _blend(
        palette.color(QPalette.ColorRole.Highlight), palette.color(QPalette.ColorRole.Base), _MARK_STRENGTH
    )
    tokens = tokenize_line(line, language)
    bounds = {start, end}
    for token in tokens:
        bounds.update((token.start, token.end))
    if mark is not None:
        bounds.update((mark[0], mark[0] + mark[1]))

    parts = [_span("…", muted)] if start > 0 else []
    edges = sorted(edge for edge in bounds if start <= edge <= end)
    for left, right in zip(edges, edges[1:]):
        token = next((token for token in tokens if token.start <= left < token.end), None)
        color = palette.color(QPalette.ColorRole.Text)
        if token is not None:
            color = syntax_color(TokenKind.STRING if token.kind == TokenKind.COLOR else token.kind)
        marked = mark is not None and mark[0] <= left < mark[0] + mark[1]
        if marked:
            color = _readable_on(color, mark_background, palette.color(QPalette.ColorRole.Text))
        parts.append(_span(line[left:right], color.name(), mark_background.name() if marked else "", marked))
    if end < len(line):
        parts.append(_span("…", muted))
    return "".join(parts)


def _shown_part(line: str, column: int, width: int) -> Tuple[int, int]:
    """:return: the start and end of the part of a line that is shown: the start of the line, or around the usage if it is cut"""
    start = max(0, column - _BEFORE_USAGE) if len(line) > width else 0
    return start, min(len(line), start + width)


def preview_html(preview: UsagePreview, language: Language, palette: QPalette) -> str:
    """:return: the lines of a preview as syntax highlighted HTML, with the usage marked and its line in a lighter background"""
    muted = palette.color(QPalette.ColorRole.PlaceholderText).name()
    line_background = _blend(palette.color(QPalette.ColorRole.Text), palette.color(QPalette.ColorRole.Base), 0.08).name()
    number_width = len(str(preview.first_line + len(preview.lines) - 1))

    rows = []
    for index, line in enumerate(preview.lines):
        is_usage = index == preview.index
        start, end = _shown_part(line, preview.column, _LINE_WIDTH) if is_usage else (0, min(len(line), _LINE_WIDTH))
        mark = (preview.column, preview.length) if is_usage else None
        number = _span(f"{preview.first_line + index:>{number_width}}  ", muted)
        background = f"background-color:{line_background};" if is_usage else ""
        code = _line_html(line, language, palette, mark, start, end)
        rows.append(f'<div style="white-space:pre;{background}">{number}{code}</div>')
    return "".join(rows)


def usage_html(usage: Usage, line: str, language: Language, palette: QPalette) -> str:
    """:return: the row of a usage in the list: its position, and its line without indentation with the usage marked"""
    indent = len(line) - len(line.lstrip())
    code = line[indent:]
    column = max(0, usage.column - indent)
    start, end = _shown_part(code, column, _LIST_WIDTH)
    position = _span(f"{usage.line}:{usage.column + 1}".ljust(8), palette.color(QPalette.ColorRole.PlaceholderText).name())
    return f'<span style="white-space:pre;">{position}{_line_html(code, language, palette, (column, usage.length), start, end)}</span>'


class UsagesPopup(QFrame):
    """
    The places a variable is used, like the list of usages of an IDE: the places grouped by file on top, the code around the
    selected one below. Select with the mouse or the keys (up, down), choose with a double click or enter; escape or a click
    elsewhere closes the popup.
    """

    def __init__(self, parent: QWidget, usages: List[Usage], config_dir: Path, chosen: Callable[[Usage], None]):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._chosen = chosen
        self._lines: Dict[Path, List[str]] = {}

        grouped = group_by_file(usages)
        title = QLabel(f"{len(usages)} usages in {len(grouped)} file{'s' if len(grouped) != 1 else ''}")
        title.setContentsMargins(6, 4, 6, 4)
        title.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        # a tint instead of the selection color, which would make the syntax colors hard to read
        palette = self.tree.palette()
        palette.setColor(
            QPalette.ColorRole.Highlight,
            _blend(palette.color(QPalette.ColorRole.Highlight), palette.color(QPalette.ColorRole.Base), _SELECTION_STRENGTH),
        )
        palette.setColor(QPalette.ColorRole.HighlightedText, palette.color(QPalette.ColorRole.Text))
        self.tree.setPalette(palette)
        self.tree.currentItemChanged.connect(self._show_preview)
        self.tree.itemActivated.connect(self._on_activated)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFrameShape(QFrame.Shape.NoFrame)
        self._preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._preview.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tree)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(title)
        layout.addWidget(splitter)

        self._fill(grouped, config_dir)

    def usage_items(self) -> List[QTreeWidgetItem]:
        """:return: the items of the usages, in the order of the list"""
        return [
            file_item.child(row)
            for index in range(self.tree.topLevelItemCount())
            for file_item in [self.tree.topLevelItem(index)]
            for row in range(file_item.childCount())
        ]

    def preview_text(self) -> str:
        """:return: the code shown for the selected usage, without the formatting"""
        return self._preview.toPlainText()

    def choose(self, item: QTreeWidgetItem):
        self.close()
        self._chosen(item.data(0, _USAGE_ROLE))

    def popup_at(self, position: QPoint):
        """Show the popup with its top left corner at the position, moved so that it is on the screen."""
        screen = self.screen().availableGeometry()
        width = min(_WIDTH, screen.width())
        height = min(_HEIGHT, int(screen.height() * _MAX_SCREEN_SHARE))
        self.resize(width, height)
        x = max(screen.left(), min(position.x(), screen.right() - width))
        y = position.y() if position.y() + height <= screen.bottom() else max(screen.top(), position.y() - height)
        self.move(x, y)
        self.show()
        items = self.usage_items()
        if items:
            self.tree.setCurrentItem(items[0])
        self.tree.setFocus()

    def _fill(self, grouped: Dict[Path, List[Usage]], config_dir: Path):
        resolved_dir = config_dir.resolve()
        for path, usages in grouped.items():
            try:
                name = path.relative_to(resolved_dir).as_posix()
            except ValueError:
                name = str(path)
            file_item = QTreeWidgetItem(self.tree, [f"{name}  ({len(usages)})"])
            font = file_item.font(0)
            font.setBold(True)
            file_item.setFont(0, font)
            self._lines[path] = path.read_text(encoding="utf-8").splitlines()
            language = language_of(path)
            for usage in usages:
                item = QTreeWidgetItem(file_item)
                item.setData(0, _USAGE_ROLE, usage)
                row = QLabel(usage_html(usage, self._lines[path][usage.line - 1], language, self.palette()))
                row.setTextFormat(Qt.TextFormat.RichText)
                row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self.tree.setItemWidget(item, 0, row)
            file_item.setExpanded(True)

    def _show_preview(self, item: Optional[QTreeWidgetItem]):
        usage: Optional[Usage] = item.data(0, _USAGE_ROLE) if item is not None else None
        if usage is None:
            self._preview.clear()
            return
        preview = preview_of(usage, self._lines[usage.path], _CONTEXT_LINES)
        self._preview.setHtml(preview_html(preview, language_of(usage.path), self.palette()))

    def _on_activated(self, item: QTreeWidgetItem):
        if item.data(0, _USAGE_ROLE) is not None:
            self.choose(item)
        else:
            item.setExpanded(not item.isExpanded())


def show_usages_popup(
    parent: QWidget, usages: List[Usage], config_dir: Path, position: QPoint, chosen: Callable[[Usage], None]
) -> UsagesPopup:
    popup = UsagesPopup(parent, usages, config_dir, chosen)
    popup.popup_at(position)
    return popup
