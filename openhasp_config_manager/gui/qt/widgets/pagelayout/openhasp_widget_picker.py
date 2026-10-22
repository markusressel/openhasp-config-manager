from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.page_objects import OpenHASPWidgetType, WIDGET_TYPES
from openhasp_config_manager.gui.qt.components import UiComponents


class OpenHASPWidgetPicker(QWidget):
    """
    The list of object types that can be added to the current page.
    """

    addItem = QtCore.pyqtSignal(OpenHASPWidgetType)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_layout()

    def _create_layout(self):
        layout = UiComponents.create_column(parent=self)
        layout.addWidget(UiComponents.create_label("Add object", role="section"))
        for widget_type, info in WIDGET_TYPES.items():
            layout.addWidget(self._create_widget_picker_button(widget_type))
        layout.addStretch(1)
        self.setFixedWidth(UiDimensions.eight * 3)

    def _create_widget_picker_button(self, widget_type: OpenHASPWidgetType) -> QWidget:
        info = WIDGET_TYPES[widget_type]
        button = UiComponents.create_button(
            title=f"{info.title}\n{info.description}",
            icon=info.icon,
            tooltip=f"Add a {info.title.lower()} ({widget_type}) to the page: {info.description.lower()}",
            variant="picker",
            on_click=lambda: self.addItem.emit(widget_type),
        )
        button.setIconSize(QtCore.QSize(UiDimensions.three, UiDimensions.three))
        return button
