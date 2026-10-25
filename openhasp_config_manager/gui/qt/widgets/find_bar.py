from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLineEdit, QPushButton, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.widgets.code_editor import CodeEditor


class FindBar(QFrame):
    """Search and replace in the text editor that is set with `set_editor` (Ctrl+F opens it, Esc closes it)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("role", "banner")
        self._editor: Optional[CodeEditor] = None

        column = UiComponents.create_column(parent=self)
        column.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)

        row = UiComponents.create_row(alignment=Qt.AlignmentFlag.AlignVCenter)
        self._find = QLineEdit()
        self._find.setPlaceholderText("Find")
        self._find.setClearButtonEnabled(True)
        self._find.textChanged.connect(self._search)
        self._find.returnPressed.connect(lambda: self._step(True))
        row.addWidget(self._find, 1)
        self._case = self._toggle("format-letter-case", "Match case")
        self._word = self._toggle("format-letter-matches", "Whole words")
        self._regex = self._toggle("regex", "Regular expression")
        for button in (self._case, self._word, self._regex):
            row.addWidget(button)
        self._status = UiComponents.create_label("", role="hint")
        row.addWidget(self._status)
        row.addWidget(self._tool("chevron-up", "Previous match (Shift+Enter)", lambda: self._step(False)))
        row.addWidget(self._tool("chevron-down", "Next match (Enter)", lambda: self._step(True)))
        row.addWidget(self._tool("close", "Close (Esc)", self.close_bar))
        column.addLayout(row)

        self._replace_row = UiComponents.create_row(alignment=Qt.AlignmentFlag.AlignVCenter)
        self._replace = QLineEdit()
        self._replace.setPlaceholderText("Replace")
        self._replace.returnPressed.connect(self._replace_one)
        self._replace_row.addWidget(self._replace, 1)
        self._replace_row.addWidget(UiComponents.create_button("Replace", self._replace_one))
        self._replace_row.addWidget(UiComponents.create_button("Replace all", self._replace_all))
        column.addLayout(self._replace_row)
        self.hide()

    def _toggle(self, icon: str, tooltip: str) -> QPushButton:
        button = self._tool(icon, tooltip, self._search)
        button.setCheckable(True)
        return button

    def _tool(self, icon: str, tooltip: str, on_click) -> QPushButton:
        button = UiComponents.create_button("", lambda: on_click(), icon=icon, tooltip=tooltip, variant="flat")
        ThemedIcons.apply(button, icon)
        return button

    def set_editor(self, editor: Optional[CodeEditor]):
        """The editor the bar searches in: the one of the current tab."""
        if self._editor is not None:
            self._editor.set_search("")
        self._editor = editor
        if editor is None:
            self.close_bar()
        elif self.isVisible():
            self._search()

    def open_bar(self):
        if self._editor is None:
            return
        selected = self._editor.textCursor().selectedText()
        if selected and " " not in selected:
            self._find.setText(selected)
        self.show()
        self._find.setFocus()
        self._find.selectAll()
        self._search()

    def close_bar(self):
        editor = self._editor
        self.hide()
        if editor is not None:
            editor.set_search("")
            editor.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._step(False)
        else:
            super().keyPressEvent(event)

    def _search(self):
        if self._editor is None:
            return
        valid = self._editor.set_search(
            self._find.text(), self._case.isChecked(), self._word.isChecked(), self._regex.isChecked()
        )
        self._find.setProperty("invalid", not valid)
        self._status.setText("Invalid expression" if not valid else "")
        self._find.style().unpolish(self._find)
        self._find.style().polish(self._find)

    def _step(self, forward: bool):
        if self._editor is None or not self._find.text():
            return
        found = self._editor.find_next(forward)
        self._status.setText("" if found else "No matches")

    def _replace_one(self):
        if self._editor is not None:
            self._editor.replace_current(self._replace.text())

    def _replace_all(self):
        if self._editor is not None:
            count = self._editor.replace_all(self._replace.text())
            self._status.setText(f"Replaced {count}")
