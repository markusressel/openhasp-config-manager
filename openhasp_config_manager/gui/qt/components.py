from collections.abc import Callable
from typing import Optional

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox, QWidget, QLineEdit, QSpinBox

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.util import parse_icons
from openhasp_config_manager.gui.qt.widgets.uicomponents.value_tracking_slider import ValueTrackingSlider


class classproperty(object):
    def __init__(self, f):
        self.f = f

    def __get__(self, obj, owner):
        return self.f(owner)


class UiComponents:
    @classproperty
    def ui_font(cls) -> QFont:
        return qta.font("mdi6", 16)

    @classmethod
    def create_label(
        cls,
        text: str,
        font: QFont = None,
        padding: int = UiDimensions.two,
    ) -> QLabel:
        label = QLabel()
        label.setText(parse_icons(text))
        label.setFont(cls.ui_font if font is None else font)
        label.setStyleSheet(f"padding: {padding}px;")
        return label

    @classmethod
    def create_button(
        cls,
        title: str,
        on_click: Callable[[], None],
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignCenter,
    ) -> QPushButton:
        button = QPushButton(parse_icons(title))
        button.setFont(cls.ui_font)
        alignment_str = {
            QtCore.Qt.AlignmentFlag.AlignLeft: "left",
            QtCore.Qt.AlignmentFlag.AlignCenter: "center",
            QtCore.Qt.AlignmentFlag.AlignRight: "right",
        }[alignment]
        button.setStyleSheet(f"padding: 10px; text-align: {alignment_str};")
        button.clicked.connect(on_click)
        return button

    @classmethod
    def create_switch(
        cls,
        title: str,
        initial_state: bool,
        on_toggle: Callable[[bool], None],
    ) -> QCheckBox:
        button = QCheckBox(parse_icons(title))
        button.setFont(cls.ui_font)
        button.setStyleSheet("padding: 10px;")
        button.setChecked(initial_state)
        button.toggled.connect(on_toggle)
        return button

    @classmethod
    def create_slider(
        cls,
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
        label.setFont(cls.ui_font)
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

    @classmethod
    def create_row(
        cls,
        parent: Optional[QWidget] = None,
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft,
        margin_start: int = 0,
        margin_end: int = 0,
        margin_top: int = 0,
        margin_bottom: int = 0,
    ) -> QHBoxLayout:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(margin_start, margin_top, margin_end, margin_bottom)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout

    @classmethod
    def create_column(
        cls,
        parent: Optional[QWidget] = None,
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignTop,
        margin_start: int = 0,
        margin_end: int = 0,
        margin_top: int = 0,
        margin_bottom: int = 0,
    ) -> QVBoxLayout:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(margin_start, margin_top, margin_end, margin_bottom)
        layout.setAlignment(alignment)
        layout.setSpacing(UiDimensions.one)
        return layout

    @classmethod
    def create_edittext(
        cls,
        text: str = "",
        padding: int = UiDimensions.one,
    ):
        line_edit = QLineEdit(text)
        line_edit.setFont(cls.ui_font)
        line_edit.setStyleSheet(f"padding: {padding}px;")
        return line_edit

    @classmethod
    def create_spinbox(
        cls,
        min_val: int = None,
        max_val: int = None,
        initial_value: int = None,
    ) -> QSpinBox:
        if min_val is None:
            min_val = -32768
        if max_val is None:
            max_val = 32767
        if initial_value is None:
            initial_value = 0

        spin = QSpinBox()
        spin.setFont(cls.ui_font)
        spin.setRange(min_val, max_val)
        spin.setValue(initial_value)
        # Style it to match your UI padding
        spin.setStyleSheet("padding: 3px; margin: 2px;")
        return spin
