from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.ui.qt.components import UiComponents


class EditorControlsWidget(QWidget):
    previousPageClicked = QtCore.pyqtSignal()
    nextPageClicked = QtCore.pyqtSignal()

    deployClicked = QtCore.pyqtSignal()
    clearClicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_layout()

    def _create_layout(self):
        self.layout = UiComponents.create_column(parent=self)

        page_controls_row = UiComponents.create_row()
        self.layout.addLayout(page_controls_row)

        self._previous_page_button_widget = UiComponents.create_button(
            title="Previous Page",
            on_click=self._on_previous_page_clicked
        )
        page_controls_row.addWidget(self._previous_page_button_widget)

        self._next_page_button_widget = UiComponents.create_button(
            title="Next Page",
            on_click=self._on_next_page_clicked,
        )
        page_controls_row.addWidget(self._next_page_button_widget)

        deployment_controls_row = UiComponents.create_row()
        self.layout.addLayout(deployment_controls_row)

        self.button_clear_page = UiComponents.create_button(
            title="Clear Page",
            on_click=self._on_clear_page_clicked
        )
        deployment_controls_row.addWidget(self.button_clear_page)

        self.button_deploy_page = UiComponents.create_button(
            title="Deploy Page",
            on_click=self._on_deploy_page_clicked
        )
        deployment_controls_row.addWidget(self.button_deploy_page)

        page_selector_widget = QWidget()

        return page_selector_widget

    def _on_previous_page_clicked(self):
        print("Previous page clicked")
        self.previousPageClicked.emit()

    def _on_next_page_clicked(self):
        print("Next page clicked")
        self.nextPageClicked.emit()

    def _on_clear_page_clicked(self):
        print("Clear page clicked")
        self.clearClicked.emit()

    def _on_deploy_page_clicked(self):
        print("Deploy page clicked")
        self.deployClicked.emit()
