from typing import Callable, List, Optional

from PyQt6.QtCore import QEvent, QObject, QStringListModel, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QCompleter, QPlainTextEdit, QWidget

from openhasp_config_manager.gui.domain.source.completion import (
    CompletionContext,
    complete,
    completion_context,
    keys_for,
    placeholder_insertion,
    property_insertion,
)
from openhasp_config_manager.gui.domain.source.docs import directive_help, object_type_at_line, placeholder_help, property_help
from openhasp_config_manager.gui.domain.source.objects import object_at_line
from openhasp_config_manager.gui.qt.widgets.hover_card import CardContent, HoverCard


class _HideWith(QObject):
    """Hides a widget whenever the watched widget is hidden."""

    def __init__(self, watched: QWidget, follower: QWidget):
        super().__init__(watched)
        self._follower = follower
        watched.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Hide:
            self._follower.hide()
        return False


class EditorCompletion(QObject):
    """
    The completion of properties, template variables and placeholders in a text editor, with the explanation of the highlighted
    entry.
    """

    def __init__(self, editor: QPlainTextEdit):
        super().__init__(editor)
        self._editor = editor
        self._variables: Callable[[], List[str]] = lambda: []
        self._include_paths: Callable[[], List[str]] = lambda: []
        self.completer = QCompleter(QStringListModel(self), editor)
        self.completer.setWidget(editor)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insert)
        # what is completed, for the explanation of the highlighted entry (the `kind` of `CompletionContext`), and the `obj` of the
        # object
        self._kind = "property"
        self._context: Optional[CompletionContext] = None
        self._object_type: Optional[str] = None
        self.card = HoverCard(editor, interactive=False)
        self._watched_popup: Optional[QWidget] = None
        self.completer.highlighted[str].connect(self._show_docs)

    @property
    def popup(self) -> QWidget:
        return self.completer.popup()

    def set_variables(self, variables: Callable[[], List[str]]):
        """The names of the template variables that can be used in this file (asked when a template is typed)."""
        self._variables = variables

    def set_include_paths(self, paths: Callable[[], List[str]]):
        """The files an `!include` can name (asked when its path is typed)."""
        self._include_paths = paths

    def show(self, force: bool = False):
        editor = self._editor
        before, _ = editor.edits.text_around_cursor()
        line_number = editor.textCursor().blockNumber() + 1
        found = object_at_line(editor.objects(), line_number)
        context = completion_context(before, editor.language, inside_object=found is not None)
        if context is None:
            self.popup.hide()
            return
        self._kind = context.kind
        self._context = context
        self._object_type = object_type_at_line(editor.objects(), line_number)
        present = [prop.key for prop in found.properties] if found is not None else []
        directive = found is not None and found.is_directive
        properties = keys_for(self._object_type, context.prefix, present, directive)
        paths = self._include_paths() if context.kind == "include" else []
        words = complete(context, properties, self._variables() if context.kind == "variable" else [], paths)
        if not words or (not force and not context.prefix):
            self.popup.hide()
            return
        self.completer.model().setStringList(words)
        self.completer.setCompletionPrefix(context.prefix)
        popup = self.popup
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = editor.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 8)
        self.completer.complete(rect)
        self._show_docs(words[0] if words else "")

    def _show_docs(self, word: str):
        """Shows what the highlighted entry of the completion list is, next to the list."""
        popup = self.popup
        if self._kind == "property":
            found = directive_help(word) or property_help(word, self._object_type)
        elif self._kind == "placeholder":
            found = placeholder_help(word, self._object_type)
        else:
            found = None
        if found is None or not popup.isVisible():
            self.card.hide()
            return
        if popup is not self._watched_popup:
            # the completer makes its list when it needs it, so it can only be watched once it shows
            self._watched_popup = popup
            _HideWith(popup, self.card)
        self.card.show_beside(popup, CardContent(help=found))

    def _insert(self, word: str):
        editor = self._editor
        cursor = editor.textCursor()
        block = cursor.block()
        context = self._context
        if self._kind == "property":
            line, column = block.text(), cursor.positionInBlock()
            insertion = property_insertion(line, column, context, word, self._object_type)
            start, end, text, after = insertion.start, insertion.end, insertion.text, insertion.cursor
        elif self._kind == "placeholder":
            insertion = placeholder_insertion(block.text(), cursor.positionInBlock(), context, word)
            start, end, text, after = insertion.start, insertion.end, insertion.text, insertion.cursor
        else:
            start, end, text = context.start, cursor.positionInBlock(), word
            after = start + len(text)
        cursor.beginEditBlock()
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        cursor.setPosition(block.position() + after)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
