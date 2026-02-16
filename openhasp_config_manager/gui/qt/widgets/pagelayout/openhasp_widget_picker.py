from enum import StrEnum

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents


class OpenHASPWidgetType(StrEnum):
    BUTTON = "button"
    LABEL = "label"
    IMAGE = "image"
    SLIDER = "slider"
    SWITCH = "switch"
    BAR = "bar"


class OpenHASPWidgetPicker(QWidget):
    addItem = QtCore.pyqtSignal(OpenHASPWidgetType)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_layout()

    def _create_layout(self):
        self.layout = UiComponents.create_column(parent=self)

        self._add_widget_picker_button(title=":mdi6.plus: Label", widget_type=OpenHASPWidgetType.LABEL)
        self._add_widget_picker_button(title=":mdi6.plus: Button", widget_type=OpenHASPWidgetType.BUTTON)
        self._add_widget_picker_button(title=":mdi6.plus: Switch", widget_type=OpenHASPWidgetType.SWITCH)
        self._add_widget_picker_button(title=":mdi6.plus: Image", widget_type=OpenHASPWidgetType.IMAGE)
        self._add_widget_picker_button(title=":mdi6.plus: Bar", widget_type=OpenHASPWidgetType.BAR)
        self._add_widget_picker_button(title=":mdi6.plus: Slider", widget_type=OpenHASPWidgetType.SLIDER)

    def _add_widget_picker_button(self, title: str, widget_type: OpenHASPWidgetType):
        def _on_button_clicked():
            print(f"Add {widget_type} button clicked")
            self.addItem.emit(widget_type)

        widget = UiComponents.create_button(
            title=title, alignment=QtCore.Qt.AlignmentFlag.AlignLeft, on_click=_on_button_clicked
        )
        self.layout.addWidget(widget)
