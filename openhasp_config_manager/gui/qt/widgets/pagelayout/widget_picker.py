from PyQt6 import QtCore
from PyQt6.QtWidgets import QFrame, QScrollArea, QStyle, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType, WIDGET_TYPES
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

        # the list scrolls: with all object types it is taller than the preview of a small window
        buttons = QWidget()
        column = UiComponents.create_column(parent=buttons)
        column.setContentsMargins(0, 0, 0, 0)
        for widget_type in WIDGET_TYPES:
            column.addWidget(self._create_widget_picker_button(widget_type))
        column.addStretch(1)
        scroll_area = QScrollArea()
        scroll_area.setWidget(buttons)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll_area, 1)
        # as wide as the buttons, and the scrollbar next to them (it shows when the list is taller than the preview)
        margins = layout.contentsMargins()
        scrollbar = scroll_area.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        self.setFixedWidth(buttons.sizeHint().width() + scrollbar + margins.left() + margins.right())

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
