from collections.abc import Callable

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox

from openhasp_config_manager.ui.dimensions import UiDimensions
from openhasp_config_manager.ui.qt.util import parse_icons


class UiComponents:

    @staticmethod
    def create_label(text: str) -> QLabel:
        label = QLabel(parse_icons(text))
        label.setFont(qta.font("mdi6", 16))
        label.setStyleSheet("padding: 10px;")
        return label

    @staticmethod
    def create_button(
        title: str,
        on_click: Callable[[], None],
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignCenter,
    ) -> QPushButton:
        button = QPushButton(parse_icons(title))
        button.setFont(qta.font("mdi6", 16))
        alignment_str = {
            QtCore.Qt.AlignmentFlag.AlignLeft: "left",
            QtCore.Qt.AlignmentFlag.AlignCenter: "center",
            QtCore.Qt.AlignmentFlag.AlignRight: "right",
        }[alignment]
        button.setStyleSheet(f"padding: 10px; text-align: {alignment_str};")
        button.clicked.connect(on_click)
        return button

    @staticmethod
    def create_switch(
        title: str,
        initial_state: bool,
        on_toggle: Callable[[bool], None]
    ) -> QCheckBox:
        button = QCheckBox(parse_icons(title))
        button.setFont(qta.font("mdi6", 16))
        button.setStyleSheet("padding: 10px;")
        button.setChecked(initial_state)
        button.toggled.connect(on_toggle)
        return button

    @staticmethod
    def create_row(
        parent=None,
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft,
    ) -> QHBoxLayout:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout

    @staticmethod
    def create_column(
        parent=None,
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignTop,
    ) -> QVBoxLayout:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout
