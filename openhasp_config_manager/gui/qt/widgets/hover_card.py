"""
The card of the text editor that explains what is under the mouse or highlighted in the completion list: the issues of the line and
what a property is and does. Like the hover of VS Code and IntelliJ it does not go away while the mouse is on it, so its text can be
selected and copied, and its links followed.
"""

import html
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source_docs import PropertyHelp
from openhasp_config_manager.gui.qt.theme import current_colors

_WIDTH = 360
_BODY_WIDTH = _WIDTH - 26  # without the margins and the border of the card
_MAX_BODY_HEIGHT = 240
_GAP = 6  # between the card and what it is about
_MARGIN = 4  # between the card and the edge of the editor
_MIN_BODY_HEIGHT = 48
_CODE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class CardContent:
    """What a card shows: problems first, then the explanation of the property."""

    issues: List[Tuple[Severity, str]] = field(default_factory=list)
    help: Optional[PropertyHelp] = None

    def is_empty(self) -> bool:
        return not self.issues and self.help is None


def _severity_color(severity: Severity) -> str:
    colors = current_colors()
    if severity == Severity.ERROR:
        return colors.error
    return colors.warning if severity == Severity.WARNING else "#8a8a8a"


def _with_alpha(color: QColor, alpha: int) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


class HoverCard(QFrame):
    """
    A card on top of the text editor (its child, not a window of its own: a window gets placed by the window manager, which often
    puts it where the mouse is). The mouse can enter it (`interactive`), then its text is selectable.
    """

    mouseEntered = pyqtSignal()
    mouseLeft = pyqtSignal()

    def __init__(self, parent: QWidget, interactive: bool = True):
        super().__init__(parent)
        self._interactive = interactive
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not interactive)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus if interactive else Qt.FocusPolicy.NoFocus)

        self._card = QFrame(self)
        self._card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self._layout = QVBoxLayout(self._card)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(8)

        self._issues = QLabel(self._card)
        self._issues.setTextFormat(Qt.TextFormat.RichText)
        self._issues.setWordWrap(True)
        self._issues.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(self._issues)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._name = QLabel(self._card)
        self._name.setObjectName("name")
        self._name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._kind = QLabel(self._card)
        self._kind.setObjectName("kind")
        header.addWidget(self._name)
        header.addStretch(1)
        header.addWidget(self._kind)
        self._header = QWidget(self._card)
        self._header.setLayout(header)
        header.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._header)

        self._body = QTextBrowser(self._card)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setOpenExternalLinks(True)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._body.document().setDocumentMargin(0)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setFixedWidth(_BODY_WIDTH)
        self._layout.addWidget(self._body)

        self._separator = QFrame(self._card)
        self._separator.setObjectName("separator")
        self._separator.setFixedHeight(1)
        self._separator.setVisible(interactive)
        self._layout.addWidget(self._separator)

        self._link = QLabel(self._card)
        self._link.setObjectName("link")
        self._link.setOpenExternalLinks(True)
        self._link.setTextFormat(Qt.TextFormat.RichText)
        self._link.setVisible(interactive)
        self._layout.addWidget(self._link)

        self.setFixedWidth(_WIDTH)
        self._key: object = None
        # the height of the text of the explanation without a limit by the room there is
        self._body_height = 0
        self.hide()

    # --- content ---

    @property
    def key(self) -> object:
        """What the card is about right now (`show_content` was given it), to not show the same again."""
        return self._key

    def show_content(self, content: CardContent, anchor: QRect, key: object = None):
        """
        :param anchor: what the card is about, in the coordinates of the parent: the card is shown above it, never on it. Below it
            if there is no room above, and with a shorter text if there is no room at all.
        :param key: any value that says what the content is about, see `key`
        """
        self._key = key
        self._style()
        self._fill(content)
        self.adjustSize()
        self.move(self._position(anchor))
        self.show()
        self.raise_()

    def _fill(self, content: CardContent):
        colors = current_colors()
        issues = content.issues
        self._issues.setVisible(bool(issues))
        self._issues.setText(
            "<br>".join(
                f'<span style="color: {_severity_color(severity)};">&#9679;</span> {self._inline(message)}'
                for severity, message in issues
            )
        )
        help_ = content.help
        for widget in (self._header, self._body):
            widget.setVisible(help_ is not None)
        has_link = self._interactive and help_ is not None and help_.url is not None
        self._link.setVisible(has_link)
        self._separator.setVisible(has_link)
        if help_ is None:
            return
        self._name.setText(html.escape(help_.name))
        self._kind.setText(html.escape(help_.kind))
        details = "".join(
            f'<tr><td style="color: {self._muted().name()}; padding-right: 10px;">{html.escape(label)}</td>'
            f"<td>{self._inline(text)}</td></tr>"
            for label, text in help_.details
        )
        self._body.setHtml(
            f"<div>{self._inline(help_.summary)}</div>"
            + (f'<table style="margin-top: 6px;">{details}</table>' if details else "")
        )
        if help_.url is not None:
            self._link.setText(
                f'<a href="{html.escape(help_.url)}" style="color: {colors.accent};">View in the openHASP docs</a>'
            )
        # measured on a copy at the final width: the widget itself only gets that width once it is laid out
        measured = self._body.document().clone(self)
        measured.setTextWidth(_BODY_WIDTH)
        height = int(measured.size().height()) + 2
        measured.deleteLater()
        self._set_body_height(min(height, _MAX_BODY_HEIGHT), height)

    def _set_body_height(self, shown: int, needed: int):
        self._body_height = shown
        self._body.setFixedHeight(shown)
        self._body.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if needed > shown else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def _limit_height(self, room: int):
        """Shortens the text, which then scrolls, if the card is higher than the room there is."""
        overflow = self.height() - room
        if overflow > 0 and self._body.isVisibleTo(self):
            needed = int(self._body.document().size().height())
            self._set_body_height(max(_MIN_BODY_HEIGHT, self._body.height() - overflow), max(needed, self._body.height()))
            self.adjustSize()

    def _inline(self, text: str) -> str:
        """Escapes a text, `code` in backticks gets the look of code, a line break stays one."""
        code = self.palette().color(QPalette.ColorRole.AlternateBase).name()
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        escaped = _CODE.sub(
            lambda match: f"<code style=\"font-family: '{mono}'; background-color: {code};\">&nbsp;{match[1]}&nbsp;</code>",
            html.escape(text),
        )
        return escaped.replace("\n", "<br>")

    def _muted(self) -> QColor:
        return self.palette().color(QPalette.ColorRole.PlaceholderText)

    def _style(self):
        palette = QApplication.palette()
        colors = current_colors()
        base = palette.color(QPalette.ColorRole.Base)
        text = palette.color(QPalette.ColorRole.Text)
        border = palette.color(QPalette.ColorRole.Mid)
        muted = self._muted()
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        self.setStyleSheet(
            f"""
            QFrame#card {{ background-color: {base.name()}; border: 1px solid {border.name()}; border-radius: 8px; }}
            QLabel, QTextBrowser {{ background: transparent; color: {text.name()}; border: none; }}
            QLabel#name {{ font-family: '{mono}'; font-weight: bold; color: {colors.accent}; }}
            QLabel#kind {{ color: {muted.name()}; background-color: {_with_alpha(muted, 40)}; border-radius: 8px; padding: 1px 8px;
                font-size: 11px; }}
            QLabel#link {{ font-size: 11px; }}
            QFrame#separator {{ background-color: {_with_alpha(muted, 50)}; border: none; }}
            """
        )

    def _position(self, anchor: QRect) -> QPoint:
        bounds = self.parentWidget().rect()
        above = anchor.top() - _GAP - _MARGIN
        below = bounds.height() - anchor.bottom() - _GAP - _MARGIN
        is_above = self.height() <= above or (self.height() > below and above >= below)
        if self.height() > (above if is_above else below):
            self._limit_height(above if is_above else below)
        x = min(max(anchor.left(), _MARGIN), max(_MARGIN, bounds.width() - self.width() - _MARGIN))
        y = anchor.top() - self.height() - _GAP if is_above else anchor.bottom() + _GAP
        return QPoint(x, y)

    def show_beside(self, popup: QWidget, content: CardContent):
        """Shows the card right of a list (left of it if there is no room), at its top. Nothing if there is no room at all."""
        parent = self.parentWidget()
        self._style()
        self._fill(content)
        self.adjustSize()
        self._limit_height(parent.height() - 2 * _MARGIN)
        left = parent.mapFromGlobal(popup.mapToGlobal(QPoint(0, 0)))
        x = left.x() + popup.width() + _GAP
        if x + self.width() > parent.width() - _MARGIN:
            x = left.x() - self.width() - _GAP
        if x < _MARGIN:
            self.hide()
            return
        self.move(x, min(max(left.y(), _MARGIN), max(_MARGIN, parent.height() - self.height() - _MARGIN)))
        self.show()
        self.raise_()

    # --- the mouse ---

    def enterEvent(self, event):
        self.mouseEntered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.mouseLeft.emit()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
