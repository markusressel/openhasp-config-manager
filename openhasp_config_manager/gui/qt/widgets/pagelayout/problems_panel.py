from typing import List

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QToolButton

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.problems import Problem, Severity
from openhasp_config_manager.gui.qt.components import ThemedIcons
from openhasp_config_manager.gui.qt.theme import current_colors

MAX_LIST_HEIGHT = UiDimensions.five * 4
LIST_WIDTH = UiDimensions.five * 10


class ProblemsPanel(QFrame):
    """
    A floating panel with the warnings and errors of the objects on the page (see `find_problems`): a header with the
    counts. Clicking it opens the list above it, over the plate, so the header stays as small as it is and the other
    floating panels don't have to make room. It is hidden while there is nothing to report.
    """

    # the object a clicked problem is about
    problemClicked = pyqtSignal(object)
    # the size or visibility changed: the preview must place its floating panels again
    layoutChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "floating")
        row = QHBoxLayout(self)
        row.setContentsMargins(UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half)

        self._header = QToolButton()
        self._header.setCheckable(True)
        self._header.setAutoRaise(True)
        self._header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._header.setToolTip("Show what is wrong with the objects on this page")
        self._header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._header.toggled.connect(self._on_toggled)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self._header)

        # shows that the panel opens: a chevron pointing where the list goes, and back when it is open
        self._chevron = QToolButton()
        self._chevron.setAutoRaise(True)
        self._chevron.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chevron.clicked.connect(self._header.toggle)
        row.addWidget(self._chevron)
        self._update_chevron()

        # a floating panel of its own, on the preview next to this one (see `_place_list`)
        self._problems: List[Problem] = []
        self._list_frame = QFrame(self)
        self._list_frame.setProperty("role", "floating")
        list_row = QHBoxLayout(self._list_frame)
        list_row.setContentsMargins(UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half)
        self._list = QListWidget()
        self._list.setFixedWidth(LIST_WIDTH)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.currentRowChanged.connect(self._on_row_changed)
        list_row.addWidget(self._list)
        self._list_frame.hide()

        self.hide()

    @staticmethod
    def _icon(severity: Severity):
        """Errors are red, warnings yellow."""
        colors = current_colors()
        if severity == Severity.ERROR:
            return qta.icon("mdi6.alert-circle", color=colors.error)
        return qta.icon("mdi6.alert", color=colors.warning)

    def refresh_theme(self):
        self.set_problems(self._problems)

    def set_problems(self, problems: List[Problem]):
        self._problems = problems
        self._list.blockSignals(True)
        self._list.clear()
        for problem in problems:
            self._list.addItem(QListWidgetItem(self._icon(problem.severity), problem.message))
        self._list.blockSignals(False)
        rows = sum(self._list.sizeHintForRow(row) for row in range(self._list.count()))
        self._list.setFixedHeight(min(MAX_LIST_HEIGHT, rows + 2 * self._list.frameWidth()))
        errors = sum(problem.severity == Severity.ERROR for problem in problems)
        warnings = len(problems) - errors
        parts = [f"{count} {name}{'' if count == 1 else 's'}" for count, name in ((errors, "error"), (warnings, "warning")) if count]
        self._header.setText(", ".join(parts))
        self._header.setIcon(self._icon(Severity.ERROR if errors else Severity.WARNING))
        self.setVisible(bool(problems))
        self._on_toggled(self._header.isChecked())

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.problemClicked.emit(self._problems[row].obj)

    def _update_chevron(self):
        opened = self._header.isChecked()
        ThemedIcons.apply(self._chevron, "chevron-down" if opened else "chevron-up")
        self._chevron.setToolTip("Hide the list" if opened else "Show what is wrong with the objects on this page")

    def _on_toggled(self, checked: bool):
        self._update_chevron()
        self._place_list()
        self.layoutChanged.emit()

    def _place_list(self):
        """Show the list above the header, if it is open, or hide it."""
        show = self._header.isChecked() and self._list.count() > 0 and not self.isHidden()
        if show:
            # a child of the preview, like this panel
            self._list_frame.setParent(self.parentWidget())
            self._list_frame.adjustSize()
            self._list_frame.move(self.x(), self.y() - self._list_frame.height() - UiDimensions.half)
            self._list_frame.raise_()
        self._list_frame.setVisible(show)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._place_list()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._list_frame.hide()
