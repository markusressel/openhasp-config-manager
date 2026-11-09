from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem, QWidget

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.page_objects import page_label
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.window.status_bar import connection_icon


@dataclass(frozen=True)
class DeviceRow:
    """A device of the config directory in the Devices panel; `connection` only while it is open (it has a tab)."""

    device: str
    connection: Optional[ConnectionStatus] = None
    live: bool = False

    @property
    def is_open(self) -> bool:
        return self.connection is not None


class DeviceAction(Enum):
    """What the context menu of a row asks for."""

    OPEN = "open"
    CLOSE = "close"
    DEPLOY = "deploy"
    RESTORE_PLATE = "restore_plate"
    REBOOT = "reboot"
    CONFIG = "config"


class DevicesPanel(QWidget):
    """
    The devices of the config directory, one row each. An open device (one with a tab) shows its plate: the connection,
    Live preview (on/off), the page the plate shows and what is wrong (e.g. pages that are out of sync); the others are
    dimmed, nothing connects to their plates. A click on a row opens the tab of its device (or focuses it), the context menu
    has what can be done with the device.
    """

    COLUMN_DEVICE, COLUMN_CONNECTION, COLUMN_LIVE, COLUMN_PAGE, COLUMN_PROBLEMS = range(5)

    # the name of the device whose row was clicked
    deviceClicked = QtCore.pyqtSignal(str)
    # (device name, on): its Live preview checkbox was toggled
    liveToggled = QtCore.pyqtSignal(str, bool)
    # (device name, DeviceAction): chosen in the context menu of its row
    actionRequested = QtCore.pyqtSignal(str, object)
    reloadClicked = QtCore.pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
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

        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(60)
        self.tree.setHeaderLabels(["Device", "Connection", "Live preview", "Page", "Problems"])
        header = self.tree.header()
        header.setStretchLastSection(True)
        for column in [self.COLUMN_DEVICE, self.COLUMN_CONNECTION, self.COLUMN_LIVE, self.COLUMN_PAGE]:
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree, 1)
        self._rows: List[DeviceRow] = []
        self._active: Optional[str] = None
        self.show_loading()

    def sizeHint(self) -> QtCore.QSize:
        """As high as its rows (at least 4), so the Files tree above it gets the rest."""
        hint = super().sizeHint()
        row_height = max(self.tree.sizeHintForRow(0), self.fontMetrics().height() + 4)
        rows = max(4, len(self._rows))
        tree = (
            self.tree.header().sizeHint().height()
            + rows * row_height
            + 2 * self.tree.frameWidth()
            # the columns are often wider than the dock
            + self.tree.horizontalScrollBar().sizeHint().height()
        )
        return QtCore.QSize(hint.width(), self._reload_button.sizeHint().height() + tree + self.layout().spacing())

    @property
    def rows(self) -> List[DeviceRow]:
        return list(self._rows)

    def show_loading(self):
        self._hint.setText("Loading devices…")
        self._hint.show()
        self._reload_button.setEnabled(False)

    def show_error(self):
        self.set_rows([])
        self._hint.setText("Could not load the devices.")

    def set_rows(self, rows: List[DeviceRow], active: Optional[str] = None):
        """
        :param rows: every device of the config directory, in the order to show them
        :param active: the device of the active tab, whose row is the current one
        """
        self._rows = list(rows)
        self._active = active
        self._reload_button.setEnabled(True)
        self._hint.setText(f"{len(rows)} device{'' if len(rows) == 1 else 's'}" if rows else "No devices found.")
        self.tree.blockSignals(True)
        self.tree.clear()
        dimmed = self.palette().placeholderText()
        for row in rows:
            item = QTreeWidgetItem([row.device, "", "", "", ""])
            item.setData(self.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole, row.device)
            if row.is_open:
                self._fill_open(item, row)
            else:
                item.setIcon(self.COLUMN_DEVICE, ThemedIcons.icon("tablet"))
                item.setText(self.COLUMN_CONNECTION, "Not open")
                item.setToolTip(self.COLUMN_DEVICE, "Click to open the device; its plate is connected while it is open")
                for column in range(self.tree.columnCount()):
                    item.setForeground(column, dimmed)
            self.tree.addTopLevelItem(item)
            if row.device == active:
                self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)

    def _fill_open(self, item: QTreeWidgetItem, row: DeviceRow):
        text, _severity = row.connection.link_summary
        if row.connection.sending:
            text = f"{text}  ·  Sending…"
        page = row.connection.page
        item.setText(self.COLUMN_CONNECTION, text)
        item.setText(self.COLUMN_PAGE, "–" if page is None else page_label(page))
        item.setText(self.COLUMN_PROBLEMS, "; ".join(row.connection.problems))
        item.setIcon(self.COLUMN_DEVICE, connection_icon(row.connection, row.live))
        item.setToolTip(self.COLUMN_CONNECTION, row.connection.details)
        item.setToolTip(self.COLUMN_PROBLEMS, row.connection.details)
        item.setToolTip(self.COLUMN_PAGE, "The page the plate reported to show last")
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(self.COLUMN_LIVE, QtCore.Qt.CheckState.Checked if row.live else QtCore.Qt.CheckState.Unchecked)
        item.setToolTip(self.COLUMN_LIVE, "Show the draft on the plate while you edit it")
        font = item.font(self.COLUMN_DEVICE)
        font.setBold(True)
        item.setFont(self.COLUMN_DEVICE, font)

    def refresh_theme(self):
        self.set_rows(self._rows, active=self._active)

    def row(self, name: str) -> Optional[DeviceRow]:
        return next((row for row in self._rows if row.device == name), None)

    @staticmethod
    def _name_of(item: QTreeWidgetItem) -> str:
        return item.data(DevicesPanel.COLUMN_DEVICE, QtCore.Qt.ItemDataRole.UserRole)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        row = self.row(self._name_of(item))
        # the checkbox of an open device only toggles Live preview
        if column != self.COLUMN_LIVE or row is None or not row.is_open:
            self.deviceClicked.emit(self._name_of(item))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column == self.COLUMN_LIVE:
            on = item.checkState(column) == QtCore.Qt.CheckState.Checked
            name = self._name_of(item)
            # later: the rows are built again then, which deletes this item
            QtCore.QTimer.singleShot(0, lambda: self.liveToggled.emit(name, on))

    def menu(self, name: str) -> QMenu:
        """The context menu of the row of a device."""
        row = self.row(name)
        menu = QMenu(self)

        def add(text: str, icon: str, action: DeviceAction, enabled: bool = True):
            entry = menu.addAction(ThemedIcons.icon(icon), text)
            entry.setEnabled(enabled)
            entry.triggered.connect(lambda _checked=False: self.actionRequested.emit(name, action))

        is_open = row is not None and row.is_open
        if is_open:
            add("Show", "tab", DeviceAction.OPEN, enabled=name != self._active)
            add("Close", "close", DeviceAction.CLOSE)
        else:
            add("Open", "tab-plus", DeviceAction.OPEN)
        live = menu.addAction(ThemedIcons.icon("broadcast"), "Live preview")
        live.setCheckable(True)
        live.setChecked(is_open and row.live)
        live.setEnabled(is_open)
        live.toggled.connect(lambda on: self.liveToggled.emit(name, on))
        menu.addSeparator()
        add("Deploy", "upload", DeviceAction.DEPLOY, enabled=is_open)
        add("Restore plate", "backup-restore", DeviceAction.RESTORE_PLATE, enabled=is_open)
        add("Reboot…", "restart", DeviceAction.REBOOT, enabled=is_open)
        menu.addSeparator()
        add("Open config.json", "cog-outline", DeviceAction.CONFIG)
        return menu

    def _on_context_menu(self, point: QtCore.QPoint):
        item = self.tree.itemAt(point)
        if item is not None:
            self.menu(self._name_of(item)).exec(self.tree.viewport().mapToGlobal(point))
