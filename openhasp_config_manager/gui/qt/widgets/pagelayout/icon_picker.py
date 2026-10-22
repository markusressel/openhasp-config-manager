from typing import Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QWidget

from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.openhasp_client.icons import IntegratedIcon


class IconPickerDialog(QDialog):
    """
    Lets the user search the icons built into openHASP. The result is the unicode character openHASP uses for it.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Insert icon")
        self.resize(360, 480)

        layout = UiComponents.create_column(parent=self)
        self._filter = UiComponents.create_edittext()
        self._filter.setPlaceholderText("Search icons…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._list = QListWidget()
        for unicode_char, icon_name in IntegratedIcon.entries():
            item = QListWidgetItem(ThemedIcons.icon(icon_name), icon_name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, unicode_char)
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_filter(self, text: str):
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(text.lower() not in item.text().lower())

    def selected_char(self) -> Optional[str]:
        item = self._list.currentItem()
        return None if item is None else item.data(QtCore.Qt.ItemDataRole.UserRole)

    @classmethod
    def pick(cls, parent: QWidget) -> Optional[str]:
        dialog = cls(parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_char()
