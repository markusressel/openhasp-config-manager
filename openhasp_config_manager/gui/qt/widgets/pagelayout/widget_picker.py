from typing import List, Tuple

from PyQt6 import QtCore
from PyQt6.QtWidgets import QFrame, QPushButton, QScrollArea, QSizePolicy, QStyle, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType, WIDGET_TYPES
from openhasp_config_manager.gui.qt.components import UiComponents


class OpenHASPWidgetPicker(QWidget):
    """
    The list of object types that can be added to the current page. Where there is not enough room for their names and
    descriptions (a small window), it shows only their icons, which leaves the preview the room.
    """

    addItem = QtCore.pyqtSignal(OpenHASPWidgetType)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: List[Tuple[QPushButton, str]] = []
        self._compact = False
        self._create_layout()

    @property
    def is_compact(self) -> bool:
        """Whether only the icons of the object types are shown (their names are in the tooltips)."""
        return self._compact

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self._full_width, super().sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact(self.width() < self._full_width)

    def _set_compact(self, compact: bool):
        if compact == self._compact:
            return
        self._compact = compact
        self._title.setText("Add" if compact else "Add object")
        for button, title in self._buttons:
            button.setText("" if compact else title)

    def _create_layout(self):
        layout = UiComponents.create_column(parent=self)
        self._title = UiComponents.create_label("Add object", role="section")
        layout.addWidget(self._title)

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
        # as wide as the buttons, and the scrollbar next to them (it shows when the list is taller than the preview): with
        # their names, or with their icons only
        margins = layout.contentsMargins()
        extra = scroll_area.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent) + margins.left() + margins.right()
        self._full_width = max(buttons.sizeHint().width(), self._title.sizeHint().width()) + extra
        self._set_compact(True)
        buttons.adjustSize()
        compact_width = max(buttons.sizeHint().width(), self._title.sizeHint().width()) + extra
        self._set_compact(False)
        self.setMinimumWidth(compact_width)
        self.setMaximumWidth(self._full_width)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

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
        self._buttons.append((button, button.text()))
        return button
