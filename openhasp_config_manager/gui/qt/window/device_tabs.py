from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from PyQt6 import QtCore
from PyQt6.QtWidgets import QTabBar

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.files import LoadedDevice
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
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
    shows it again without loading anything. The tabs of a device share what was loaded of it, its draft and its connection.
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
        # files that changed on disk while the tab was in the background: applied when it is shown again
        self.changed_files: Set[Path] = set()
        # what the title of the tab shows (see `DeviceTabs.update_title`)
        self.dirty = False
        self.connection = ConnectionStatus()

    @property
    def title(self) -> str:
        return self.name


class PartTab(DeviceTab):
    """
    A part tab ("Edit the part", see `MainWindow.edit_part`): one instance of a part of a device, its objects alone or on its
    page (dimmed). It owns its part mode (`focus`), in the draft of the pages of the device, or in a draft of the part on its
    own (`load_part_alone`) if no page of the device includes it.
    """

    def __init__(self, name: str, editor: PageLayoutEditorWidget, part: Path, focus: PartFocus):
        super().__init__(name, editor)
        # resolved
        self.part = part
        self.focus = focus

    @property
    def alone(self) -> bool:
        """Whether the part is shown on its own, in a draft of its own that is in no file."""
        return self.focus.session.is_part_alone

    @property
    def title(self) -> str:
        return f"{self.part.name} · {self.name}"


class DeviceTabs(QtCore.QObject):
    """
    The tabs above the preview: one per open device (its pages), and the part tabs (`PartTab`). Each has its own
    `PageLayoutEditorWidget`, made by `create_editor`.
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
        """:return: the tab of the pages of a device"""
        return next((tab for tab in self.tabs if tab.name == name and not isinstance(tab, PartTab)), None)

    def find_part(self, name: str, part: Path) -> Optional[PartTab]:
        """:return: the part tab of a part (resolved) of a device"""
        return next((tab for tab in self.tabs if isinstance(tab, PartTab) and tab.name == name and tab.part == part), None)

    def of_device(self, name: str) -> List[DeviceTab]:
        """:return: the tabs of a device: of its pages and of its parts"""
        return [tab for tab in self.tabs if tab.name == name]

    def tab_of(self, editor: PageLayoutEditorWidget) -> Optional[DeviceTab]:
        return next((tab for tab in self.tabs if tab.editor is editor), None)

    def open(self, name: str) -> DeviceTab:
        """A new tab for the pages of a device, which becomes the active one."""
        tab = DeviceTab(name, self._take_editor())
        self._add(tab, len(self.tabs))
        self.activate(tab)
        return tab

    def open_part(self, name: str, part: Path, focus: PartFocus) -> PartTab:
        """A new part tab of a device, next to the active tab. It becomes the active one when the caller activates it."""
        tab = PartTab(name, self._take_editor(), part, focus)
        self._add(tab, len(self.tabs) if self.active is None else self.tabs.index(self.active) + 1)
        return tab

    def _take_editor(self) -> PageLayoutEditorWidget:
        editor, self._spare = self._spare or self._create_editor(), None
        return editor

    def _add(self, tab: DeviceTab, index: int):
        self.tabs.insert(index, tab)
        self.bar.blockSignals(True)
        self.bar.insertTab(index, tab.title)
        self.bar.blockSignals(False)
        self.update_title(tab)
        self.bar.show()
        self.opened.emit(tab)

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
        The title of a tab: its device (and part), marked if the files it shows have unsaved changes, with a dot for the
        connection to the plate (the Live preview icon while it is on), the details in the tooltip.
        """
        index = self.tabs.index(tab)
        live = tab.editor.plate.live
        self.bar.setTabText(index, f"{tab.title} {DIRTY_MARK}" if tab.dirty else tab.title)
        self.bar.setTabIcon(index, connection_icon(tab.connection, live))
        what = tab.name
        if isinstance(tab, PartTab):
            where = "on its own" if tab.alone else f"at {tab.focus.describe() or '–'}"
            what = f"The part {tab.part.name} of {tab.name}, {where}"
        lines = [
            f"{what}: unsaved changes" if tab.dirty else what,
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
