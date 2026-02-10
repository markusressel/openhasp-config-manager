from collections.abc import Callable

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.util import parse_icons
from openhasp_config_manager.gui.qt.widgets.uicomponents.value_tracking_slider import ValueTrackingSlider


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
        slider_widget = QWidget()
        main_layout = QHBoxLayout(slider_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(UiDimensions.one)

        # 1. Title Label
        label = QLabel(parse_icons(title))
        label.setFont(qta.font("mdi6", 16))
        label.setStyleSheet("padding: 10px;")
        main_layout.addWidget(label)

        # 2. Slider Container (to hold min label, slider, and max label)
        slider_container = QHBoxLayout()

        min_label = QLabel(str(min_value))
        min_label.setStyleSheet("color: gray; font-size: 10px;")

        max_label = QLabel(str(max_value))
        max_label.setStyleSheet("color: gray; font-size: 10px;")

        # Use our custom subclass
        slider = ValueTrackingSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(initial_value)
        slider.valueChanged.connect(on_change)

        # Optional: Increase height to make room for the floating text
        slider.setMinimumHeight(50)

        slider_container.addWidget(min_label)
        slider_container.addWidget(slider)
        slider_container.addWidget(max_label)

        main_layout.addLayout(slider_container)

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
