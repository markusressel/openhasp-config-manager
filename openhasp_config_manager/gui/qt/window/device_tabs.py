from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from PyQt6 import QtCore
from PyQt6.QtWidgets import QTabBar

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.files import LoadedDevice
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.window.status_bar import connection_icon
from openhasp_config_manager.gui.qt.widgets.message_panel import MessagePanel
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.openhasp_client.model.device import Device

# marks a tab with unsaved changes
DIRTY_MARK = "•"


class DeviceTab:
    """
    An open device: its own editor (page, zoom, mode, selection), and what was loaded of the device, so switching to the tab
    shows it again without loading anything.
    """

    def __init__(self, name: str, editor: PageLayoutEditorWidget):
        self.name = name
        self.editor = editor
        # None while the device is loading, or if it couldn't be loaded
        self.device: Optional[Device] = None
        self.loaded: Optional[LoadedDevice] = None
        self.pages_data: Optional[OpenHaspDevicePagesData] = None
        # the (device name, cmd component) of the draft in the editor (see `MainWindow.sessions`)
        self.session_key: Optional[Tuple[str, str]] = None
        # what the center shows instead of the editor while the device is loading or failed to load, None for the editor
        self.message: Optional[Callable[[MessagePanel], None]] = None
        # counts the loads of the device: the result of an older one is dropped
        self.load_generation = 0
        # the draft of a part that no page of the device includes, shown on its own instead of the pages (see
        # `MainWindow.edit_part_alone`), its path and the page of the device to go back to
        self.part_alone: Optional[PlateSession] = None
        self.part_alone_path: Optional[Path] = None
        self.page_before_part_alone: Optional[int] = None
        # files that changed on disk while the tab was in the background: applied when it is shown again
        self.changed_files: Set[Path] = set()
        # what the title of the tab shows (see `DeviceTabs.update_title`)
        self.dirty = False
        self.connection = ConnectionStatus()


class DeviceTabs(QtCore.QObject):
    """
    The tabs above the preview, one per open device. Each has its own `PageLayoutEditorWidget`, made by `create_editor`.
    There is always an editor for the window to show, also without a tab: the one of the last closed tab, cleared, which the
    next tab takes.
    """

    # (the active tab, the one that was active before), each None if there is none
    activated = QtCore.pyqtSignal(object, object)
    # a tab was opened, before it becomes the active one
    opened = QtCore.pyqtSignal(object)
    # the × of a tab was clicked: the window decides (see `close`)
    closeRequested = QtCore.pyqtSignal(object)

    def __init__(self, create_editor: Callable[[], PageLayoutEditorWidget], parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._create_editor = create_editor
        self.tabs: List[DeviceTab] = []
        self.active: Optional[DeviceTab] = None
        # the editor without a tab, None while every editor has one
        self._spare: Optional[PageLayoutEditorWidget] = create_editor()

        self.bar = QTabBar()
        self.bar.setTabsClosable(True)
        self.bar.setMovable(True)
        self.bar.setDocumentMode(True)
        self.bar.setExpanding(False)
        self.bar.setUsesScrollButtons(True)
        self.bar.setElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self.bar.hide()
        self.bar.currentChanged.connect(self._on_current_changed)
        self.bar.tabCloseRequested.connect(lambda index: self.closeRequested.emit(self._tab_at(index)))
        self.bar.tabMoved.connect(self._on_tab_moved)

    @property
    def editor(self) -> PageLayoutEditorWidget:
        """The editor the window shows: of the active tab, or the spare one without a tab."""
        return self._spare if self.active is None else self.active.editor

    @property
    def editors(self) -> List[PageLayoutEditorWidget]:
        return [tab.editor for tab in self.tabs] + ([] if self._spare is None else [self._spare])

    def find(self, name: str) -> Optional[DeviceTab]:
        return next((tab for tab in self.tabs if tab.name == name), None)

    def tab_of(self, editor: PageLayoutEditorWidget) -> Optional[DeviceTab]:
        return next((tab for tab in self.tabs if tab.editor is editor), None)

    def open(self, name: str) -> DeviceTab:
        """A new tab for a device, which becomes the active one."""
        editor, self._spare = self._spare or self._create_editor(), None
        tab = DeviceTab(name, editor)
        self.tabs.append(tab)
        self.bar.blockSignals(True)
        self.bar.addTab(name)
        self.bar.blockSignals(False)
        self.update_title(tab)
        self.bar.show()
        self.opened.emit(tab)
        self.activate(tab)
        return tab

    def activate(self, tab: DeviceTab):
        if tab is self.active:
            return
        previous, self.active = self.active, tab
        self.bar.blockSignals(True)
        self.bar.setCurrentIndex(self.tabs.index(tab))
        self.bar.blockSignals(False)
        self.activated.emit(tab, previous)

    def close(self, tab: DeviceTab) -> Optional[PageLayoutEditorWidget]:
        """
        Remove a tab; the tab next to it becomes the active one.
        :return: its editor, to be deleted by the caller; None if it is kept as the spare one (the last tab was closed)
        """
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        self.bar.blockSignals(True)
        self.bar.removeTab(index)
        self.bar.blockSignals(False)
        editor = tab.editor
        if not self.tabs:
            self._spare, editor = editor, None
            self.bar.hide()
        if tab is self.active:
            self.active = None
            following = self.tabs[min(index, len(self.tabs) - 1)] if self.tabs else None
            if following is None:
                self.activated.emit(None, tab)
            else:
                self.activate(following)
        return editor

    def set_dirty(self, tab: DeviceTab, dirty: bool):
        """Mark the title of a tab whose drafts have unsaved changes."""
        tab.dirty = dirty
        self.update_title(tab)

    def set_connection(self, tab: DeviceTab, status: ConnectionStatus):
        """Show the connection to the plate of a tab in its dot."""
        tab.connection = status
        self.update_title(tab)

    def update_title(self, tab: DeviceTab):
        """
        The title of a tab: its device, marked if its drafts have unsaved changes, with a dot for the connection to the plate
        (the Live preview icon while it is on), the details in the tooltip.
        """
        index = self.tabs.index(tab)
        live = tab.editor.plate.live
        self.bar.setTabText(index, f"{tab.name} {DIRTY_MARK}" if tab.dirty else tab.name)
        self.bar.setTabIcon(index, connection_icon(tab.connection, live))
        lines = [
            f"{tab.name}: unsaved changes" if tab.dirty else tab.name,
            "",
            tab.connection.summary[0],
            tab.connection.details,
        ]
        if live:
            lines.append("Live preview is on: the draft is sent to the plate while you edit it, also from other tabs.")
        self.bar.setTabToolTip(index, "\n".join(lines))

    def refresh_theme(self):
        for tab in self.tabs:
            self.update_title(tab)

    def title(self, tab: DeviceTab) -> str:
        return self.bar.tabText(self.tabs.index(tab))

    def _tab_at(self, index: int) -> DeviceTab:
        return self.tabs[index]

    def _on_current_changed(self, index: int):
        if 0 <= index < len(self.tabs):
            self.activate(self.tabs[index])

    def _on_tab_moved(self, source: int, target: int):
        self.tabs.insert(target, self.tabs.pop(source))
