from typing import Callable, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QEvent, QObject, QRect
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.widgets.hover_card import CardContent, HoverCard

# the same delays as the hover of the text editor (`code_editor/hover.py`)
_HOVER_DELAY_MS = 120
_HOVER_GRACE_MS = 300


class PropertyLabelHover(QObject):
    """
    The card that explains a property when the mouse rests on its name in the properties panel, like the hover of the text editor.
    It is a child of the window, not of the panel: the panel is too narrow for it. It stays while the mouse is on the name or on
    the card, so its text can be selected and its link followed.
    """

    def __init__(self, panel: QWidget):
        super().__init__(panel)
        self._panel = panel
        self._card: Optional[HoverCard] = None
        # the label the mouse is on, and what to show for it
        self._label: Optional[QWidget] = None
        self._contents: dict = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_HOVER_DELAY_MS)
        self._timer.timeout.connect(self._show)
        self.grace_timer = QtCore.QTimer(self)
        self.grace_timer.setSingleShot(True)
        self.grace_timer.setInterval(_HOVER_GRACE_MS)
        self.grace_timer.timeout.connect(self.hide)

    @property
    def card(self) -> Optional[HoverCard]:
        return self._card

    def watch(self, label: QWidget, content: Callable[[], CardContent]):
        """Explains what `content` returns while the mouse rests on the label."""
        self._contents[label] = content
        label.installEventFilter(self)

    def reset(self):
        """Forgets the watched labels, before the panel makes them again (e.g. after an edit), and hides the card."""
        self._contents.clear()
        self._label = None
        self.hide()

    def eventFilter(self, watched, event):
        # Qt still sends the events of the labels while the window is torn down, after the Python part of this object is gone
        contents = self.__dict__.get("_contents")
        if contents is not None and watched in contents:
            if event.type() == QEvent.Type.Enter:
                self.grace_timer.stop()
                self._label = watched
                self._timer.start()
            elif event.type() == QEvent.Type.Leave:
                self._timer.stop()
                if self._card is not None and self._card.isVisible():
                    self.grace_timer.start()
        return False

    def _show(self):
        label = self._label
        if label is not None and label.underMouse():
            self.show_for(label)

    def show_for(self, label: QWidget):
        """Shows the card of a watched label, next to it."""
        content = self._contents[label]()
        if content.is_empty():
            return
        window = self._panel.window()
        if self._card is None or self._card.parentWidget() is not window:
            self._card = HoverCard(window, interactive=True)
            self._card.mouseEntered.connect(self.grace_timer.stop)
            self._card.mouseLeft.connect(self.grace_timer.start)
        if self._card.isVisible() and self._card.key is label:
            return
        anchor = QRect(label.mapTo(window, label.rect().topLeft()), label.size())
        self._card.show_content(content, anchor, key=label)

    def hide(self):
        self._timer.stop()
        self.grace_timer.stop()
        if self._card is not None:
            self._card.hide()
