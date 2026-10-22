import html
from typing import Any, List, Sequence, Tuple

from PyQt6 import QtCore
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QTextDocument, QPalette, QColor
from PyQt6.QtWidgets import QCompleter, QLineEdit, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.fuzzy import filter_template_suggestions, template_query
from openhasp_config_manager.gui.qt.theme import current_colors

_TEMPLATE_ROLE = QtCore.Qt.ItemDataRole.UserRole
_VALUE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
_POSITIONS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2

# the longest value shown next to a suggestion
_MAX_VALUE_LENGTH = 40
_MIN_POPUP_WIDTH = 420


class TemplateCompleter(QtCore.QObject):
    """
    Suggests template variables for a template field: fuzzy matched against what was typed (without the braces),
    best match first, with the matched characters highlighted. Choosing one replaces the text of the field.
    """

    def __init__(self, editor: QLineEdit, suggestions: Sequence[Tuple[str, Any]]):
        super().__init__(editor)
        self._editor = editor
        self._suggestions = suggestions
        self._model = QStandardItemModel(self)

        self._completer = QCompleter(self)
        self._completer.setWidget(editor)
        self._completer.setModel(self._model)
        # the model is filtered and sorted here, the completer only shows it
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._completer.setMaxVisibleItems(12)
        # keep a reference: the view does not own its delegate, without it the Python part is collected
        self._delegate = _HighlightDelegate(self._completer.popup())
        self._completer.popup().setItemDelegate(self._delegate)
        self._completer.activated[QtCore.QModelIndex].connect(self._on_activated)

        editor.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text: str):
        matches = filter_template_suggestions(template_query(text), self._suggestions)
        self._model.clear()
        for match in matches:
            item = QStandardItem(match.template)
            item.setData(match.template, _TEMPLATE_ROLE)
            item.setData(_format_value(match.value), _VALUE_ROLE)
            item.setData(list(match.positions), _POSITIONS_ROLE)
            self._model.appendRow(item)

        popup = self._completer.popup()
        if not matches:
            popup.hide()
            return
        width = max(self._editor.width(), _MIN_POPUP_WIDTH)
        self._completer.complete(QtCore.QRect(0, 0, width, self._editor.height()))
        popup.setCurrentIndex(self._model.index(0, 0))

    def _on_activated(self, index: QtCore.QModelIndex):
        self._editor.setText(index.data(_TEMPLATE_ROLE))
        self._editor.setFocus()


def _format_value(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= _MAX_VALUE_LENGTH else text[: _MAX_VALUE_LENGTH - 1] + "…"


def suggestion_html(template: str, positions: List[int], value: str, match_color: str, value_color: str) -> str:
    """The text of a suggestion, with the characters that matched the query highlighted."""
    matched = set(positions)
    parts = []
    for index, char in enumerate(template):
        escaped = html.escape(char)
        parts.append(f'<b style="color: {match_color};">{escaped}</b>' if index in matched else escaped)
    return f'{"".join(parts)}&nbsp;&nbsp;&nbsp;<span style="color: {value_color};">= {html.escape(value)}</span>'


class _HighlightDelegate(QStyledItemDelegate):
    def _document(self, option: QStyleOptionViewItem, index: QtCore.QModelIndex) -> QTextDocument:
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        palette = option.palette
        text_color = palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        value_color = QColor(text_color)
        value_color.setAlpha(150)

        document = QTextDocument()
        document.setDocumentMargin(UiDimensions.half)
        document.setDefaultFont(option.font)
        document.setDefaultStyleSheet(f"body {{ color: {text_color.name()}; }}")
        document.setHtml(
            "<body>"
            + suggestion_html(
                template=index.data(_TEMPLATE_ROLE),
                positions=index.data(_POSITIONS_ROLE),
                value=index.data(_VALUE_ROLE),
                match_color=text_color.name() if selected else current_colors().warning,
                value_color=value_color.name(QColor.NameFormat.HexArgb),
            )
            + "</body>"
        )
        return document

    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        document = self._document(option, index)
        # the background and selection of the item, without its text
        option.text = ""
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        painter.save()
        painter.translate(option.rect.left(), option.rect.top() + (option.rect.height() - document.size().height()) / 2)
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        document = self._document(option, index)
        return QtCore.QSize(int(document.idealWidth()), int(document.size().height()))
