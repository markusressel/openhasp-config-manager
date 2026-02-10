from collections.abc import Callable

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.util import parse_icons


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
    def create_slider(
        title: str,
        on_change: Callable[[int], None],
        initial_value: int = 0,
        min_value: int = 0,
        max_value: int = 100,
    ):
        from PyQt6.QtWidgets import QSlider, QWidget, QHBoxLayout, QLabel
        slider_widget = QWidget()
        layout = QHBoxLayout(slider_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(UiDimensions.one)

        label = QLabel(parse_icons(title))
        label.setFont(qta.font("mdi6", 16))
        label.setStyleSheet("padding: 10px;")
        layout.addWidget(label)

        slider = QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(initial_value)
        slider.valueChanged.connect(on_change)
        layout.addWidget(slider)

        return slider_widget

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
