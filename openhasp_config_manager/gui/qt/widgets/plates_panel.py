from dataclasses import dataclass
from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.page_objects import page_label
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.window.status_bar import connection_icon


@dataclass(frozen=True)
class PlateRow:
    """An open device in the Plates panel."""

    device: str
    connection: ConnectionStatus
    live: bool


class PlatesPanel(QWidget):
    """
    The plates of the open devices, one row each: the connection, Live preview (on/off), the page the plate shows and what is
    wrong (e.g. pages that are out of sync). A click on a row focuses the tab of its device.
    """

    COLUMN_DEVICE, COLUMN_CONNECTION, COLUMN_LIVE, COLUMN_PAGE, COLUMN_PROBLEMS = range(5)

    # the name of the device whose row was clicked
    deviceClicked = QtCore.pyqtSignal(str)
    # (device name, on): its Live preview checkbox was toggled
    liveToggled = QtCore.pyqtSignal(str, bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = UiComponents.create_column(parent=self)
        self._hint = UiComponents.create_label("Open a device to connect to its plate.", role="hint", word_wrap=True)
        layout.addWidget(self._hint)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setHeaderLabels(["Device", "Connection", "Live preview", "Page", "Problems"])
        header = self.tree.header()
        header.setStretchLastSection(True)
        for column in [self.COLUMN_DEVICE, self.COLUMN_CONNECTION, self.COLUMN_LIVE, self.COLUMN_PAGE]:
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)
        self._rows: List[PlateRow] = []

    @property
    def rows(self) -> List[PlateRow]:
        return list(self._rows)

    def set_rows(self, rows: List[PlateRow], active: Optional[str] = None):
        """:param active: the device of the active tab, whose row is the current one"""
        self._rows = list(rows)
        self._hint.setVisible(not rows)
        self.tree.blockSignals(True)
        self.tree.clear()
        for row in rows:
            text, _severity = row.connection.link_summary
            if row.connection.sending:
                text = f"{text}  ·  Sending…"
            page = row.connection.page
            item = QTreeWidgetItem(
                [row.device, text, "", "–" if page is None else page_label(page), "; ".join(row.connection.problems)]
            )
            item.setData(self.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole, row.device)
            item.setIcon(self.COLUMN_DEVICE, connection_icon(row.connection, row.live))
            item.setToolTip(self.COLUMN_CONNECTION, row.connection.details)
            item.setToolTip(self.COLUMN_PROBLEMS, row.connection.details)
            item.setToolTip(self.COLUMN_PAGE, "The page the plate reported to show last")
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(self.COLUMN_LIVE, QtCore.Qt.CheckState.Checked if row.live else QtCore.Qt.CheckState.Unchecked)
            item.setToolTip(self.COLUMN_LIVE, "Show the draft on the plate while you edit it")
            self.tree.addTopLevelItem(item)
            if row.device == active:
                self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)

    def refresh_theme(self):
        self.set_rows(self._rows, active=self._current_device())

    def _current_device(self) -> Optional[str]:
        item = self.tree.currentItem()
        return None if item is None else item.data(self.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        if column != self.COLUMN_LIVE:
            self.deviceClicked.emit(item.data(self.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column == self.COLUMN_LIVE:
            on = item.checkState(column) == QtCore.Qt.CheckState.Checked
            name = item.data(self.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole)
            # later: the rows are built again then, which deletes this item
            QtCore.QTimer.singleShot(0, lambda: self.liveToggled.emit(name, on))
