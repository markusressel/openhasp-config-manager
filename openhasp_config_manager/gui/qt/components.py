import weakref
from collections.abc import Callable
from typing import Optional, List, Tuple

import qtawesome as qta
from PyQt6 import QtCore, sip
from PyQt6.QtGui import QAction, QIcon, QPalette
from PyQt6.QtWidgets import (
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QWidget,
    QLineEdit,
    QSpinBox,
    QAbstractButton,
    QApplication,
)

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.icons import parse_icons
from openhasp_config_manager.gui.qt.widgets.uicomponents.value_tracking_slider import ValueTrackingSlider


class ThemedIcons:
    """
    qtawesome icons are rendered in a fixed color. This keeps track of the widgets and actions that show one,
    so they can be re-rendered in the text color of the new palette when the theme changes.
    """

    _targets: List[Tuple[weakref.ref, str, Optional[int]]] = []

    @classmethod
    def icon(cls, name: str) -> QIcon:
        palette = QApplication.palette()
        return qta.icon(
            f"mdi6.{name}",
            color=palette.color(QPalette.ColorRole.WindowText),
            color_disabled=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText),
        )

    @classmethod
    def apply(cls, target: QAction | QAbstractButton | QLabel, name: str, size: Optional[int] = None):
        cls._targets.append((weakref.ref(target), name, size))
        cls._apply(target, name, size)

    @classmethod
    def refresh(cls):
        alive = []
        for ref, name, size in cls._targets:
            target = ref()
            if target is None or sip.isdeleted(target):
                continue
            cls._apply(target, name, size)
            alive.append((ref, name, size))
        cls._targets = alive

    @classmethod
    def _apply(cls, target, name: str, size: Optional[int]):
        icon = cls.icon(name)
        if isinstance(target, QLabel):
            target.setPixmap(icon.pixmap(size or UiDimensions.three))
        else:
            target.setIcon(icon)


class UiComponents:
    @classmethod
    def create_label(
        cls,
        text: str,
        role: Optional[str] = None,
        word_wrap: bool = False,
    ) -> QLabel:
        """
        :param role: the style role of the label (title, section, hint, error), see theme.py
        """
        label = QLabel(text)
        label.setWordWrap(word_wrap)
        if role is not None:
            label.setProperty("role", role)
        return label

    @classmethod
    def create_icon_label(cls, icon: str, size: int = UiDimensions.three) -> QLabel:
        label = QLabel()
        ThemedIcons.apply(label, icon, size)
        label.setProperty("role", "icon")
        return label

    @classmethod
    def create_button(
        cls,
        title: str,
        on_click: Callable[[], None],
        icon: Optional[str] = None,
        tooltip: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> QPushButton:
        """
        :param icon: the name of an mdi6 icon
        :param variant: the style variant of the button (danger, flat, picker), see theme.py
        """
        button = QPushButton(title)
        if icon is not None:
            ThemedIcons.apply(button, icon)
        if tooltip is not None:
            button.setToolTip(tooltip)
        if variant is not None:
            button.setProperty("variant", variant)
        button.clicked.connect(lambda _checked=False: on_click())
        return button

    @classmethod
    def create_action(
        cls,
        parent: QtCore.QObject,
        title: str,
        icon: str,
        on_trigger: Callable[[], None] = None,
        shortcut: Optional[str | QtCore.QKeyCombination] = None,
        tooltip: Optional[str] = None,
        checkable: bool = False,
        context: QtCore.Qt.ShortcutContext = QtCore.Qt.ShortcutContext.WindowShortcut,
    ) -> QAction:
        action = QAction(title, parent)
        ThemedIcons.apply(action, icon)
        action.setCheckable(checkable)
        action.setShortcutContext(context)
        if shortcut is not None:
            action.setShortcut(shortcut)
        tooltip = tooltip or title
        if shortcut is not None:
            tooltip = f"{tooltip} ({action.shortcut().toString()})"
        action.setToolTip(tooltip)
        if on_trigger is not None:
            action.triggered.connect(lambda _checked=False: on_trigger())
        return action

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

        main_layout.addWidget(cls.create_label(parse_icons(title)))

        min_label = cls.create_label(str(min_value), role="hint")
        max_label = cls.create_label(str(max_value), role="hint")

        slider = ValueTrackingSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(initial_value)
        slider.valueChanged.connect(on_change)
        # room for the value drawn above the handle
        slider.setMinimumHeight(UiDimensions.five)

        main_layout.addWidget(min_label)
        main_layout.addWidget(slider, 1)
        main_layout.addWidget(max_label)

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
    def create_edittext(cls, text: str = "") -> QLineEdit:
        return QLineEdit(text)

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
        spin.setRange(min_val, max_val)
        spin.setValue(initial_value)
        return spin
