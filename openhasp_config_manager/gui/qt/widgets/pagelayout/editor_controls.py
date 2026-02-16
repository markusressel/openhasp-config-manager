from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents


class EditorControlsWidget(QWidget):
    previousPageClicked = QtCore.pyqtSignal()
    nextPageClicked = QtCore.pyqtSignal()
    syncWithRealDeviceToggled = QtCore.pyqtSignal(bool)

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
            title=":mdi6.chevron-left: Previous Page",
            on_click=self._on_previous_page_clicked,
        )
        page_controls_row.addWidget(self._previous_page_button_widget)

        self._next_page_button_widget = UiComponents.create_button(
            title="Next Page :mdi6.chevron-right:",
            on_click=self._on_next_page_clicked,
        )
        page_controls_row.addWidget(self._next_page_button_widget)

        self._sync_with_real_device_switch = UiComponents.create_switch(
            title=":mdi6.sync: Sync with Real Device",
            initial_state=False,
            on_toggle=lambda state: self.syncWithRealDeviceToggled.emit(state),
        )
        page_controls_row.addWidget(self._sync_with_real_device_switch)

        deployment_controls_row = UiComponents.create_row()
        self.layout.addLayout(deployment_controls_row)

        self.button_clear_page = UiComponents.create_button(
            title=":mdi6.eraser: Clear Page",
            on_click=self._on_clear_page_clicked,
        )
        deployment_controls_row.addWidget(self.button_clear_page)

        self.button_deploy_page = UiComponents.create_button(
            title=":mdi6.upload: Deploy Page",
            on_click=self._on_deploy_page_clicked,
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

    def is_sync_with_real_device_enabled(self) -> bool:
        return self._sync_with_real_device_switch.isChecked()
