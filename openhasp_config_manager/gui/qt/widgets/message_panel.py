from typing import Callable, List, Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QProgressBar, QFrame, QVBoxLayout, QHBoxLayout, QSizePolicy

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.layouts import clear_layout

# (title, mdi6 icon, callback)
type PanelAction = Tuple[str, str, Callable[[], None]]


class MessagePanel(QWidget):
    """
    A centered placeholder for loading, empty and error states.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # centered with stretches: alignment flags on the layouts would keep the word-wrapped labels from growing in height
        outer = QVBoxLayout(self)
        outer.setContentsMargins(UiDimensions.three, UiDimensions.three, UiDimensions.three, UiDimensions.three)
        outer.addStretch(1)
        row = QHBoxLayout()
        outer.addLayout(row)
        outer.addStretch(1)

        content = QWidget()
        content.setMaximumWidth(520)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addStretch(1)
        row.addWidget(content, 100)
        row.addStretch(1)
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(UiDimensions.two)

        self._icon = UiComponents.create_label("")
        self._icon.setProperty("role", "icon")
        self._icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self._icon)

        self._title = UiComponents.create_label("", role="title", word_wrap=True)
        self._title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self._title)

        self._text = UiComponents.create_label("", role="hint", word_wrap=True)
        self._text.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._text.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self._text)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(UiDimensions.one)
        column.addWidget(self._progress)

        self._actions = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        column.addLayout(self._actions)

    def show_loading(self, title: str, text: str = ""):
        self._show(icon="progress-clock", title=title, text=text, loading=True, actions=[])

    def show_message(self, icon: str, title: str, text: str = "", actions: List[PanelAction] = ()):
        self._show(icon=icon, title=title, text=text, loading=False, actions=actions)

    def show_error(self, title: str, error: str, retry: Optional[Callable[[], None]] = None):
        actions = [("Retry", "refresh", retry)] if retry is not None else []
        self._show(icon="alert-circle-outline", title=title, text=error, loading=False, actions=actions, is_error=True)

    def _show(self, icon: str, title: str, text: str, loading: bool, actions: List[PanelAction], is_error: bool = False):
        self._icon.setPixmap(ThemedIcons.icon(icon).pixmap(UiDimensions.eight))
        self._title.setText(title)
        # lets long paths wrap at their separators
        self._text.setText(text.replace("/", "/\u200b"))
        self._text.setVisible(bool(text))
        self._text.setProperty("role", "error" if is_error else "hint")
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)
        self._progress.setVisible(loading)

        clear_layout(self._actions)
        for action_title, action_icon, callback in actions:
            self._actions.addWidget(UiComponents.create_button(title=action_title, icon=action_icon, on_click=callback))


class ErrorBanner(QFrame):
    """
    An inline error message with a retry and a dismiss button, e.g. for a failed deploy.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "banner")
        self._retry: Optional[Callable[[], None]] = None

        row = UiComponents.create_row(parent=self, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        row.addWidget(UiComponents.create_icon_label("alert-circle-outline"))
        self._text = UiComponents.create_label("", word_wrap=True)
        self._text.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._text, 1)
        self._retry_button = UiComponents.create_button(title="Retry", icon="refresh", on_click=self._on_retry)
        row.addWidget(self._retry_button)
        row.addWidget(UiComponents.create_button(title="", icon="close", tooltip="Dismiss", on_click=self.hide))
        self.hide()

    def show_error(self, text: str, retry: Optional[Callable[[], None]] = None):
        # lets long paths wrap at their separators
        self._text.setText(text.replace("/", "/\u200b"))
        self._retry = retry
        self._retry_button.setVisible(retry is not None)
        self.show()

    def _on_retry(self):
        self.hide()
        if self._retry is not None:
            self._retry()


class DiskChangesBanner(QFrame):
    """
    Tells that files of the draft changed on disk (e.g. edited by an LLM or in a text editor) while the draft has
    unsaved changes of its own, and lets the user choose which side to keep.
    """

    reloadRequested = QtCore.pyqtSignal()
    visibilityChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "banner")

        row = UiComponents.create_row(parent=self, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        row.addWidget(UiComponents.create_icon_label("file-alert-outline"))
        self._text = UiComponents.create_label("", word_wrap=True)
        self._text.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._text, 1)
        row.addWidget(
            UiComponents.create_button(
                title="Reload from disk",
                icon="refresh",
                tooltip="Discard the changes of the draft and load the files as they are on disk now",
                on_click=self._on_reload,
            )
        )
        row.addWidget(
            UiComponents.create_button(
                title="Keep my changes",
                icon="close",
                tooltip="Keep the draft. Save fails for files that changed on disk, until the draft is reverted.",
                on_click=self.hide,
            )
        )
        self.hide()

    def show_changes(self, files: List[str]):
        shown = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
        # lets long paths wrap at their separators
        self._text.setText(f"Changed on disk since this draft was loaded: {shown}".replace("/", "/​"))
        self.show()

    def setVisible(self, visible: bool):
        # also while the window is not shown (show() and hide() end up here)
        super().setVisible(visible)
        self.visibilityChanged.emit()

    def _on_reload(self):
        self.hide()
        self.reloadRequested.emit()
