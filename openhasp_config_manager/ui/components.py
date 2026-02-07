from collections.abc import Callable

from PyQt6 import QtCore
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout

from openhasp_config_manager.ui.dimensions import UiDimensions


class UiComponents:

    @staticmethod
    def create_button(title: str, on_click: Callable[[], None]) -> QPushButton:
        button = QPushButton(title)
        button.setStyleSheet("padding: 10px;")
        button.clicked.connect(on_click)
        return button

    @staticmethod
    def create_row(
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignCenter,
    ) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout

    @staticmethod
    def create_column(
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignCenter,
    ) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout
