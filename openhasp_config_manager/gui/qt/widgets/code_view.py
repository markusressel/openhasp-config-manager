from enum import StrEnum

from PyQt6 import QtCore
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu, QSplitter, QToolButton, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.widgets.source_editor import SourceEditorWidget

_MODE_KEY = "code_view/mode"
_ORIENTATION_KEY = "code_view/orientation"
_SPLITTER_KEY = "code_view/splitter"
_WRAP_KEY = "code_view/word_wrap"
_VALUES_KEY = "code_view/template_values"
_WHITESPACE_KEY = "code_view/whitespace"


class CodeViewMode(StrEnum):
    SOURCE = "source"
    SPLIT = "split"
    RENDERED = "rendered"


class CodeView(QWidget):
    """
    The files as text. Like the design/code views of Android Studio, one view shows either the source (the text
    editor for the files, as written, with their templates), the rendered JSONL of the file in the current tab (what its templates
    make of it), or both side by side (or above each other), with a splitter between them. The JSONL of the whole page, from all
    files, is the "Page JSONL" dock.
    """

    modeChanged = QtCore.pyqtSignal(object)

    def __init__(self, source: SourceEditorWidget, rendered: QWidget, parent=None):
        super().__init__(parent)
        self.source = source
        self.rendered = rendered
        self._mode = CodeViewMode.RENDERED

        column = UiComponents.create_column(parent=self)
        column.setSpacing(0)

        bar = QWidget()
        row = UiComponents.create_row(parent=bar, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.setContentsMargins(UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half)
        self._group = QActionGroup(self)
        self._buttons = {}
        for mode, title, icon, tooltip in (
            (CodeViewMode.SOURCE, "Source", "file-code-outline", "Edit the files as written, with their templates"),
            (CodeViewMode.SPLIT, "Split", "view-split-vertical", "Source and rendered side by side"),
            (
                CodeViewMode.RENDERED,
                "Rendered",
                "eye-outline",
                "The JSONL of the file in the current tab, with its templates rendered",
            ),
        ):
            action = UiComponents.create_action(self, title, icon, tooltip=tooltip, checkable=True)
            action.triggered.connect(lambda _checked=False, mode=mode: self.set_mode(mode))
            self._group.addAction(action)
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            row.addWidget(button)
            self._buttons[mode] = action
        row.addStretch(1)

        self._orientation_action = UiComponents.create_action(
            self,
            "Side by side",
            "swap-horizontal",
            on_trigger=self._toggle_orientation,
            tooltip="Switch between source and rendered side by side, or above each other",
        )
        orientation = QToolButton()
        orientation.setDefaultAction(self._orientation_action)
        row.addWidget(orientation)

        menu = QMenu(self)
        self._wrap_action = QAction("Word wrap", menu, checkable=True)
        self._wrap_action.toggled.connect(self._set_word_wrap)
        self._whitespace_action = QAction("Show whitespace", menu, checkable=True)
        self._whitespace_action.toggled.connect(self._set_whitespace)
        self._values_action = QAction("Show template values", menu, checkable=True)
        self._values_action.setToolTip("Show what the templates of a line render to after the line")
        self._values_action.toggled.connect(self._set_values)
        zoom_reset = QAction("Reset zoom (Ctrl+wheel zooms)", menu)
        zoom_reset.triggered.connect(self._reset_zoom)
        for action in (self._wrap_action, self._whitespace_action, self._values_action, zoom_reset):
            menu.addAction(action)
        options = QToolButton()
        ThemedIcons.apply(options, "dots-vertical")
        options.setToolTip("Editor options")
        options.setMenu(menu)
        options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(options)
        column.addWidget(bar)

        self._splitter = QSplitter()
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(source)
        self._splitter.addWidget(rendered)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        column.addWidget(self._splitter, 1)

        settings = QSettings()
        self._splitter.setOrientation(
            Qt.Orientation.Vertical
            if settings.value(_ORIENTATION_KEY, "horizontal") == "vertical"
            else Qt.Orientation.Horizontal
        )
        state = settings.value(_SPLITTER_KEY)
        if state is not None:
            self._splitter.restoreState(state)
        self._wrap_action.setChecked(settings.value(_WRAP_KEY, False, type=bool))
        self._whitespace_action.setChecked(settings.value(_WHITESPACE_KEY, False, type=bool))
        self._values_action.setChecked(settings.value(_VALUES_KEY, False, type=bool))
        mode = settings.value(_MODE_KEY, CodeViewMode.RENDERED.value)
        self.set_mode(CodeViewMode(mode) if mode in CodeViewMode._value2member_map_ else CodeViewMode.RENDERED)
        self._update_orientation_action()

    @property
    def mode(self) -> CodeViewMode:
        return self._mode

    @property
    def shows_source(self) -> bool:
        return self._mode != CodeViewMode.RENDERED

    def set_mode(self, mode: CodeViewMode):
        self._mode = mode
        self._buttons[mode].setChecked(True)
        self.source.setVisible(mode != CodeViewMode.RENDERED)
        self.rendered.setVisible(mode != CodeViewMode.SOURCE)
        self._orientation_action.setEnabled(mode == CodeViewMode.SPLIT)
        QSettings().setValue(_MODE_KEY, mode.value)
        self.modeChanged.emit(mode)

    def show_source(self):
        """Make the source visible (next to the rendered view if that is shown)."""
        if self._mode == CodeViewMode.RENDERED:
            self.set_mode(CodeViewMode.SPLIT)

    def save_state(self):
        QSettings().setValue(_SPLITTER_KEY, self._splitter.saveState())

    def _toggle_orientation(self):
        vertical = self._splitter.orientation() == Qt.Orientation.Horizontal
        self._splitter.setOrientation(Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal)
        QSettings().setValue(_ORIENTATION_KEY, "vertical" if vertical else "horizontal")
        self._update_orientation_action()

    def _update_orientation_action(self):
        side_by_side = self._splitter.orientation() == Qt.Orientation.Horizontal
        self._orientation_action.setText("Side by side" if side_by_side else "Stacked")
        ThemedIcons.apply(self._orientation_action, "view-split-vertical" if side_by_side else "view-split-horizontal")

    def _set_word_wrap(self, wrap: bool):
        self.source.set_word_wrap(wrap)
        QSettings().setValue(_WRAP_KEY, wrap)

    def _set_values(self, show: bool):
        self.source.set_show_values(show)
        QSettings().setValue(_VALUES_KEY, show)

    def _set_whitespace(self, show: bool):
        self.source.set_show_whitespace(show)
        QSettings().setValue(_WHITESPACE_KEY, show)

    def _reset_zoom(self):
        editor = self.source.current_editor
        if editor is not None:
            editor.reset_zoom()
