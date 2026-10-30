import html
from pathlib import Path
from typing import List

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openhasp_config_manager.check import Issue
from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.theme import current_colors

ICON_SIZE = UiDimensions.three


class DeployProblemsDialog(QDialog):
    """
    What a deployment of a device failed on (see `check_device_files`): every error, where it is, and how to fix it. The
    location of an error opens the file at its line. It doesn't block the window, so the files can be fixed while it is open.
    """

    # a location was clicked: the file (absolute) and the line (starting at 1, None for the whole file)
    openRequested = pyqtSignal(object, object)

    def __init__(self, device: str, config_dir: Path, issues: List[Issue], parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self.setWindowTitle(f"Can't deploy {device}")
        self.setMinimumWidth(UiDimensions.eight * 10)

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Nothing was uploaded to {device}: its files can't be processed. Fix the errors below, then deploy again."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        entries = QWidget()
        entries_layout = QVBoxLayout(entries)
        entries_layout.setContentsMargins(0, 0, 0, 0)
        entries_layout.setSpacing(UiDimensions.two)
        for index, issue in enumerate(issues):
            entries_layout.addWidget(self._entry(index, issue))
        entries_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(entries)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _entry(self, index: int, issue: Issue) -> QWidget:
        entry = QWidget()
        row = QHBoxLayout(entry)
        row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.alert-circle", color=current_colors().error).pixmap(ICON_SIZE, ICON_SIZE))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon)

        column = QVBoxLayout()
        message = QLabel(html.escape(issue.message))
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(message)
        if issue.file is not None:
            location = ":".join(str(part) for part in (issue.file, issue.line) if part is not None)
            link = QLabel(f'<a href="{index}">{html.escape(location)}</a>')
            link.setToolTip("Open the file at this line")
            link.linkActivated.connect(lambda _, i=issue: self.openRequested.emit(self._config_dir / i.file, i.line))
            column.addWidget(link)
        for hint in issue.hints:
            label = QLabel(f"• {html.escape(hint)}")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            column.addWidget(label)
        row.addLayout(column, stretch=1)
        return entry
