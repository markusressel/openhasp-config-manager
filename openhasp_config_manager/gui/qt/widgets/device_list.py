from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QListWidget, QListWidgetItem

from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.openhasp_client.model.device import Device


class DeviceListWidget(QWidget):
    """
    The devices of the config directory. Emits the name of the selected device, because the Device objects
    are created anew every time the config directory is analyzed.
    """

    deviceSelected = QtCore.pyqtSignal(str)
    reloadClicked = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = UiComponents.create_column(parent=self)

        # the dock is titled "Devices" already
        header = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._hint = UiComponents.create_label("", role="hint", word_wrap=True)
        header.addWidget(self._hint, 1)
        self._reload_button = UiComponents.create_button(
            title="",
            icon="refresh",
            tooltip="Reload the config directory (Ctrl+R)",
            on_click=self.reloadClicked.emit,
        )
        header.addWidget(self._reload_button)
        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, 1)

        self.show_loading()

    def show_loading(self):
        self._hint.setText("Loading devices…")
        self._reload_button.setEnabled(False)

    def show_error(self):
        self._list.clear()
        self._hint.setText("Could not load the devices.")
        self._reload_button.setEnabled(True)

    def set_devices(self, devices: List[Device], selected: Optional[str] = None):
        self._reload_button.setEnabled(True)
        self._list.clear()
        for device in sorted(devices, key=lambda d: d.name):
            item = QListWidgetItem(ThemedIcons.icon("tablet"), device.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, device.name)
            item.setToolTip(str(device.path))
            self._list.addItem(item)
            if device.name == selected:
                self._list.setCurrentItem(item)

        self._hint.setText(f"{len(devices)} device{'' if len(devices) == 1 else 's'}" if devices else "No devices found.")

    def _on_item_clicked(self, item: QListWidgetItem):
        self.deviceSelected.emit(item.data(QtCore.Qt.ItemDataRole.UserRole))
