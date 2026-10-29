import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, List, Dict, Set, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QWidget,
    QMainWindow,
    QStackedWidget,
    QDockWidget,
    QSplitter,
    QMessageBox,
    QVBoxLayout,
)
from openhasp_config_manager.const import DEVICES_FOLDER_NAME, COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.draft.files import (
    LoadedDevice,
    load_device,
    load_part_alone,
)
from openhasp_config_manager.gui.domain.config_changes import OwnWrites
from openhasp_config_manager.gui.domain.connection import ConnectionStatus, LinkState
from openhasp_config_manager.gui.domain.live_preview import live_preview_refusal
from openhasp_config_manager.gui.domain.gui_state import (
    GuiStateFile,
    now,
)
from openhasp_config_manager.gui.domain.draft.config_draft import ConfigDraft
from openhasp_config_manager.gui.domain.draft.model import PartInstance
from openhasp_config_manager.gui.domain.draft.page_objects import get_navigable_page_indices
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.components import ThemedIcons
from openhasp_config_manager.gui.qt.config_watcher import ConfigWatcher
from openhasp_config_manager.gui.qt.preview_image import png_bytes, render_plate
from openhasp_config_manager.gui.qt.window.gui_state_publisher import GuiStatePublisher
from openhasp_config_manager.gui.qt.window.device_logs import DeviceLogs
from openhasp_config_manager.gui.qt.window.device_tabs import DeviceTab, DeviceTabs, PartTab
from openhasp_config_manager.gui.qt.window.draft_actions import DraftActions
from openhasp_config_manager.gui.qt.window.file_actions import FileActions
from openhasp_config_manager.gui.qt.window.gui_state_collector import collect_gui_state
from openhasp_config_manager.gui.qt.window.log_colors import LogColors
from openhasp_config_manager.gui.qt.window.menus import create_menus, show_editor_actions
from openhasp_config_manager.gui.qt.window.source_sync import SourceEditorSync
from openhasp_config_manager.gui.qt.window.status_bar import StatusBarController
from openhasp_config_manager.gui.qt.connection import ConnectionController, PlateConnections
from openhasp_config_manager.gui.qt.log_stream import LogStreamController
from openhasp_config_manager.gui.qt.widgets.log_view import LogView
from openhasp_config_manager.gui.qt.operations import OperationStatus, error_text
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.theme import ThemeMode, apply_theme
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.widgets.source.code_view import CodeView
from openhasp_config_manager.gui.qt.widgets.source.rendered_view import FileRenderedView
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.source.file_tree import FileTreeWidget
from openhasp_config_manager.gui.qt.widgets.message_panel import MessagePanel, DiskConflictBanner, file_list_text
from openhasp_config_manager.gui.qt.widgets.plates_panel import PlateRow, PlatesPanel
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.plate_link import PlateLink
from openhasp_config_manager.gui.qt.widgets.source.source_editor import SourceEditorWidget
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device

LOGGER = logging.getLogger(__name__)

# the version of the saved arrangement of the docks: a state of another version is not restored
DOCK_STATE_VERSION = 3


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.cfg_root = Path(config_manager.cfg_root).resolve()
        self.devices: List[Device] = []
        # the files as the drafts have them, shared by the drafts of all devices: a file is loaded once
        self.config_draft = ConfigDraft()
        # one draft per (device name, cmd component): the Device objects are created anew on every reload
        # they stay when the tab of the device is closed
        self.sessions: Dict[Tuple[str, str], PlateSession] = {}
        # the page to show after a draft was reloaded (saved or reverted), per session key
        self._page_after_reload: Dict[Tuple[str, str], int] = {}
        # counts the loads of each device (by its name): the result of an older one is dropped
        self._load_generations: Dict[str, int] = {}
        self._discard_drafts_on_close = False
        # what the app wrote itself (Save), to tell its own file changes from those of others
        self.own_writes = OwnWrites()
        # a reload after files changed on disk is running, and more changed meanwhile
        self._reloading_changes: Optional[Set[Path]] = None
        self._changes_during_reload: Set[Path] = set()
        # for the state file (see `collect_gui_state`)
        self.load_error: Optional[Dict[str, Any]] = None
        self.last_operation: Optional[Dict[str, Any]] = None
        self.disk_changes: List[str] = []
        # select the device of the last session once the devices are loaded the first time
        self._restore_selection = True
        # what is restored on the next start: the selected device, the file for new objects, ...
        self.ui_session = UiSessionStore(Path(config_manager.cfg_root), QSettings())

        self.status = OperationStatus(self)
        self.status.succeeded.connect(lambda message: self._on_operation(True, message))
        self.status.failed.connect(lambda description, error: self._on_operation(False, f"{description}: {error}"))
        # tells tools that edit the config files next to the GUI what the user has open
        self._state_publisher = GuiStatePublisher(
            GuiStateFile(self.cfg_root),
            lambda running=True: collect_gui_state(self, running),
            # and what they look like
            preview=lambda: png_bytes(render_plate(self.page_layout_editor_widget.page_preview_widget)),
            parent=self,
        )

        self.setWindowTitle("openhasp-config-manager")
        self.setMinimumSize(960, 600)
        self.setDockNestingEnabled(True)

        self.create_basic_layout()
        self.draft_actions = DraftActions(self)
        self.file_actions = FileActions(self)
        self.file_tree_widget.fileActionRequested.connect(self.file_actions.request)
        create_menus(self)
        self._update_draft_actions()
        # the arrangement of the docks as built above, before the saved one is restored
        self._default_dock_state = self.saveState(DOCK_STATE_VERSION)
        self._restore_window_state()
        # the editor starts in interact mode, which has nothing to show in the properties
        self.properties_dock.hide()
        self.load_plates()
        self._start_watching_config_dir()
        self.source_sync.restore_open_files()
        self._state_publisher.request()

    # --- layout ---

    def create_basic_layout(self):
        # the editors of the tabs show their properties and JSONL in these docks, each the one of the active tab
        self.properties_stack = QStackedWidget()
        self.page_jsonl_stack = QStackedWidget()
        # a placeholder (no device, loading, errors) or the editor of the active tab
        self.message_panel = MessagePanel()
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.message_panel)
        # one tab per open device, each with its own editor
        self.device_tabs = DeviceTabs(self._create_editor, parent=self)
        self.device_tabs.opened.connect(self._on_tab_opened)
        self.device_tabs.activated.connect(self._on_tab_activated)
        self.device_tabs.closeRequested.connect(self.close_tab)
        self._toolbar = self.page_layout_editor_widget.toolbar
        self.addToolBar(self._toolbar)

        # all panels are docks, so each can be moved: the central widget is only there for Qt
        central = QWidget()
        central.hide()
        self.setCentralWidget(central)

        # files changed on disk while the draft has changes of its own
        self.disk_changes_banner = DiskConflictBanner(
            reload_tooltip="Discard the changes of the draft and load the files as they are on disk now",
            keep_title="Keep my changes",
            keep_tooltip="Keep the draft. Save fails for files that changed on disk, until the draft is reverted.",
        )
        self.disk_changes_banner.reloadRequested.connect(self.reload_draft)
        self.disk_changes_banner.visibilityChanged.connect(self._state_publisher.request)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.device_tabs.bar)
        center_layout.addWidget(self.disk_changes_banner)
        center_layout.addWidget(self.center_stack, 1)

        # left: devices and their files
        self.device_list_widget = DeviceListWidget()
        self.device_list_widget.deviceSelected.connect(self.on_device_selected)
        self.device_list_widget.reloadClicked.connect(self.load_plates)

        # the files of the device of the active tab, and which of them new objects go into
        self.file_tree_widget = FileTreeWidget()
        self.file_tree_widget.highlightRequested.connect(lambda key: self.page_layout_editor_widget.highlight_component(key))
        self.file_tree_widget.targetRequested.connect(lambda key: self.page_layout_editor_widget.set_target_component(key))

        self.sidebar = QSplitter(Qt.Orientation.Vertical)
        self.sidebar.addWidget(self.device_list_widget)
        self.sidebar.addWidget(self.file_tree_widget)
        # the file tree grows with the window
        self.sidebar.setStretchFactor(1, 1)
        self.sidebar.setChildrenCollapsible(False)
        self.sidebar.setMinimumWidth(260)
        self.devices_dock = self._add_dock("Devices", "devices_dock", self.sidebar)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.devices_dock)

        # center: the render preview. It can't be closed: there is nothing to do without it
        self.preview_dock = self._add_dock("Preview", "preview_dock", center, closable=False)
        self.splitDockWidget(self.devices_dock, self.preview_dock, Qt.Orientation.Horizontal)

        # right: the properties of the selected object
        self.properties_dock = self._add_dock("Properties", "properties_dock", self.properties_stack)
        self.splitDockWidget(self.preview_dock, self.properties_dock, Qt.Orientation.Horizontal)

        # below the preview: the files as text (source), and the JSONL of the page (rendered)
        self.source_editor = SourceEditorWidget(self.cfg_root)
        self.source_editor.saved.connect(self._on_source_saved)
        self.source_editor.stateChanged.connect(self._state_publisher.request)
        self.source_editor.openFailed.connect(lambda path, message: self.status.failed.emit(f"Opening {path.name}", message))
        # the rendered view of the code view follows the file in the current tab, the page view is a dock of its own
        self.file_rendered = FileRenderedView()
        self.code_view = CodeView(self.source_editor, self.file_rendered)
        self.code_view.modeChanged.connect(lambda _mode: self._state_publisher.request())
        self.source_sync = SourceEditorSync(
            self.source_editor,
            self.code_view,
            self.page_layout_editor_widget,
            lambda: self.session,
            self.ui_session,
            self.cfg_root,
            self.file_rendered,
            parent=self,
        )
        self.file_tree_widget.openRequested.connect(self.source_sync.open_file)
        self.file_tree_widget.editPartRequested.connect(lambda part: self.edit_part(part))
        self.source_editor.set_part_check(self.file_tree_widget.is_part_file)
        self.source_editor.editPartRequested.connect(lambda part: self.edit_part(part))
        self.jsonl_dock = self._add_dock("Code", "jsonl_dock", self.code_view)
        self.splitDockWidget(self.preview_dock, self.jsonl_dock, Qt.Orientation.Vertical)

        # the JSONL of the page in the preview: the objects of all files that contribute to it, the way the plate gets them
        self.page_jsonl_dock = self._add_dock("Page JSONL", "page_jsonl_dock", self.page_jsonl_stack)
        self.tabifyDockWidget(self.jsonl_dock, self.page_jsonl_dock)

        # the logs of the plates of the tabs, next to the code. Closed at first: they hold the only telnet connection a plate
        # allows while the dock is open.
        self.log_colors = LogColors(self)
        self.device_logs = DeviceLogs(on_enable_colors=self.log_colors.ask, parent=self)
        self.logs_dock = self._add_dock("Logs", "logs_dock", self.device_logs.stack)
        self.tabifyDockWidget(self.jsonl_dock, self.logs_dock)
        self.jsonl_dock.raise_()
        self.logs_dock.hide()
        # open, also while another dock of its tab group is raised
        self.logs_dock.toggleViewAction().toggled.connect(self.device_logs.set_open)

        # the plates of the open devices: their connection, Live preview, the page they show and what is wrong
        self.plates_panel = PlatesPanel()
        self.plates_panel.deviceClicked.connect(lambda name: self.device_tabs.activate(self.device_tabs.find(name)))
        self.plates_panel.liveToggled.connect(self.set_live_preview)
        self.plates_dock = self._add_dock("Plates", "plates_dock", self.plates_panel)
        self.tabifyDockWidget(self.jsonl_dock, self.plates_dock)
        self.jsonl_dock.raise_()
        self._size_docks()

        self.status_bar = StatusBarController(
            self, self.status, on_resync=lambda index: self.page_layout_editor_widget.resync_page(index)
        )

        # one connection and one PlateLink per open device, also while its tabs are in the background
        self.connections = PlateConnections(self._create_link, self)
        self.connections.changed.connect(self._on_connection_changed)
        # what the status bar shows without a tab
        self._no_connection = ConnectionController(self)
        self.status_bar.set_connection(self._no_connection.status)

    @property
    def connection(self) -> ConnectionController:
        """The connection to the plate of the active tab (one without a device if there is no tab)."""
        tab = self.device_tabs.active
        return self._no_connection if tab is None else self.connections.get(tab.name)

    @property
    def log_view(self) -> LogView:
        """The log of the device of the active tab (an empty one without a tab)."""
        return self.device_logs.active.view

    @property
    def log_stream(self) -> LogStreamController:
        return self.device_logs.active.stream

    @property
    def page_layout_editor_widget(self) -> PageLayoutEditorWidget:
        """The editor of the active tab (one without a draft if there is no tab)."""
        return self.device_tabs.editor

    def _create_editor(self) -> PageLayoutEditorWidget:
        """An editor for a tab. What it reports reaches the window only while its tab is the active one."""
        editor = PageLayoutEditorWidget(status=self.status, ui_session=self.ui_session)

        def active(slot):
            return lambda *args: slot(*args) if editor is self.page_layout_editor_widget else None

        editor.pageChanged.connect(active(lambda index, count: self.status_bar.set_page(index, count)))
        editor.dirtyChanged.connect(active(lambda dirty: self.status_bar.set_dirty(dirty)))
        editor.dirtyChanged.connect(active(lambda _: self._update_draft_actions()))
        editor.dirtyChanged.connect(lambda _: self._update_tab_title(self.device_tabs.tab_of(editor)))
        editor.stateChanged.connect(active(self._state_publisher.request))
        editor.dirtyChanged.connect(active(lambda _: self._state_publisher.request()))
        editor.pageChanged.connect(active(lambda *_: self._state_publisher.request()))
        editor.selectedObjectComponentChanged.connect(active(lambda key: self.file_tree_widget.reveal(key)))
        editor.fileStateChanged.connect(active(self._update_file_tree_state))
        editor.editPartRequested.connect(active(lambda part, instance: self.edit_part(part, instance, editor.session)))
        editor.partDone.connect(active(lambda: self.close_tab(self.device_tabs.active)))
        editor.action_edit_mode.toggled.connect(active(self._on_edit_mode_toggled))
        for busy in [editor.busy, editor.device_controls.busy]:
            busy.changed.connect(lambda _: self._update_sending(editor))
            busy.changed.connect(active(lambda _: self._update_draft_actions()))
        self.center_stack.addWidget(editor)
        self.properties_stack.addWidget(editor.property_editor)
        self.page_jsonl_stack.addWidget(editor.jsonl_preview)
        return editor

    def _create_link(self, name: str) -> PlateLink:
        """What the tabs of a device do on its plate: what is sent counts for the device, also from a tab in the background."""
        link = PlateLink(self, status=self.status)
        link.pageOutOfSync.connect(lambda page: self.connections.get(name).page_out_of_sync(page))
        link.pageDeployed.connect(lambda page: self.connections.get(name).page_deployed(page))
        link.plateRestored.connect(lambda: self.connections.get(name).plate_restored())
        link.liveChanged.connect(lambda _: self._on_live_changed(name))
        link.set_live_guard(lambda: self._live_preview_refusal(name))
        return link

    def _delete_editor(self, editor: PageLayoutEditorWidget):
        """The editor of a closed tab."""
        for stack, widget in [
            (self.center_stack, editor),
            (self.properties_stack, editor.property_editor),
            (self.page_jsonl_stack, editor.jsonl_preview),
        ]:
            stack.removeWidget(widget)
            widget.deleteLater()
        editor.toolbar.deleteLater()

    def _show_editor(self, editor: PageLayoutEditorWidget):
        """The toolbar, the menus and the docks show those of the editor of the active tab."""
        if self._toolbar is not editor.toolbar:
            self.removeToolBar(self._toolbar)
            self._toolbar = editor.toolbar
            self.addToolBar(self._toolbar)
            self._toolbar.show()
        show_editor_actions(self, editor)
        self.properties_stack.setCurrentWidget(editor.property_editor)
        self.page_jsonl_stack.setCurrentWidget(editor.jsonl_preview)
        self.properties_dock.setVisible(editor.edit_mode)
        self.source_sync.set_page_editor(editor)

    def _on_edit_mode_toggled(self, enabled: bool):
        # the properties can only be changed in edit mode
        self.properties_dock.setVisible(enabled)

    def _size_docks(self):
        self.resizeDocks([self.preview_dock, self.jsonl_dock], [520, 280], Qt.Orientation.Vertical)
        self.resizeDocks(
            [self.devices_dock, self.preview_dock, self.properties_dock], [280, 700, 360], Qt.Orientation.Horizontal
        )

    def _add_dock(self, title: str, name: str, widget: QWidget, closable: bool = True) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        features = QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        if closable:
            features |= QDockWidget.DockWidgetFeature.DockWidgetClosable
        dock.setFeatures(features)
        return dock

    def _update_file_tree_state(self):
        if self.page_layout_editor_widget.session is not None:
            self.file_tree_widget.update_state(*self.page_layout_editor_widget.file_state())

    def _update_sending(self, editor: PageLayoutEditorWidget):
        self._with_connection(
            editor, lambda connection: connection.set_sending(editor.busy.busy or editor.device_controls.busy.busy)
        )

    def _with_connection(self, editor: PageLayoutEditorWidget, action):
        """Do something with the connection of the device of an editor; nothing for the editor without a tab."""
        tab = self.device_tabs.tab_of(editor)
        if tab is not None:
            action(self.connections.get(tab.name))

    def set_theme(self, mode: ThemeMode):
        apply_theme(mode)
        ThemedIcons.refresh()
        self.status_bar.refresh_theme()
        self.file_tree_widget.refresh_theme()
        self.file_rendered.view.refresh_theme()
        self.source_editor.refresh_theme()
        self.device_logs.refresh_theme()
        self.device_tabs.refresh_theme()
        self.plates_panel.refresh_theme()
        for editor in self.device_tabs.editors:
            editor.jsonl_preview.refresh_theme()
            editor.problems_panel.refresh_theme()
            editor.page_preview_widget.viewport().update()

    # --- window state ---

    def _restore_window_state(self):
        settings = QSettings()
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1440, 900)
        state = settings.value("window/state")
        if state is not None:
            self.restoreState(state, DOCK_STATE_VERSION)
        sidebar = settings.value("window/sidebar")
        if sidebar is None or not self.sidebar.restoreState(sidebar):
            # once the window has its size: the device list compact, the file tree takes the rest
            QtCore.QTimer.singleShot(0, self._size_sidebar)

    def restore_default_layout(self):
        for dock in [
            self.devices_dock,
            self.preview_dock,
            self.properties_dock,
            self.jsonl_dock,
            self.page_jsonl_dock,
            self.logs_dock,
            self.plates_dock,
        ]:
            dock.setFloating(False)
        self.restoreState(self._default_dock_state, DOCK_STATE_VERSION)
        self._size_docks()
        self._size_sidebar()

    def _size_sidebar(self):
        total = sum(self.sidebar.sizes())
        devices = 130
        self.sidebar.setSizes([devices, max(120, total - devices)])

    def quit_discarding_drafts(self):
        """Close without asking about unsaved drafts, e.g. on SIGTERM: the drafts are lost."""
        dirty = self._dirty_draft_names()
        if dirty:
            LOGGER.warning(f"Quitting, discarding the unsaved changes of: {', '.join(dirty)}")
        self._discard_drafts_on_close = True
        self.close()

    def _dirty_draft_names(self) -> List[str]:
        names = [f"{device} ({cmd})" for (device, cmd), session in self.sessions.items() if session.is_dirty]
        for tab in self.device_tabs.tabs:
            if isinstance(tab, PartTab) and tab.alone and tab.focus.session.is_dirty:
                names.append(f"{tab.part.name} (part)")
        return names

    def closeEvent(self, event):
        dirty = self._dirty_draft_names() + [f"{path.name} (text editor)" for path in self.source_editor.dirty_files()]
        if dirty and not self._discard_drafts_on_close:
            answer = QMessageBox.question(
                self,
                "Unsaved changes",
                "These drafts have changes that are not saved:\n\n" + "\n".join(dirty) + "\n\nDiscard them and quit?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.connections.stop()
        self.device_logs.stop()
        self._watcher.stop()
        self._state_publisher.stop()
        self.code_view.save_state()
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState(DOCK_STATE_VERSION))
        settings.setValue("window/sidebar", self.sidebar.saveState())
        super().closeEvent(event)

    # --- devices ---

    def load_plates(self):
        """Analyze the config directory in the background and show its devices."""
        self.device_list_widget.show_loading()
        if self.device is None:
            self.message_panel.show_loading("Loading devices…", str(self.config_manager.cfg_root))
            self.center_stack.setCurrentWidget(self.message_panel)

        async def __analyze():
            return await asyncio.to_thread(self.config_manager.analyze)

        run_async(__analyze(), on_success=self._on_devices_loaded, on_error=self._on_devices_failed)

    def _on_devices_loaded(self, devices: List[Device]):
        self._set_devices(devices)
        if not devices:
            devices_dir = Path(self.config_manager.cfg_root, DEVICES_FOLDER_NAME)
            self.message_panel.show_message(
                icon="tablet-cellphone",
                title="No devices found",
                text=f"openhasp-config-manager looks for devices in\n{devices_dir}\n\n"
                f"Create one folder per plate there, containing the plate's config.json "
                f'(see the README, section "Folder Structure"), then reload.',
                actions=[("Reload", "refresh", self.load_plates)],
            )
            self.center_stack.setCurrentWidget(self.message_panel)
            return
        restore, self._restore_selection = self._restore_selection, False
        if self.device_tabs.active is not None:
            if self.device is None:
                # loading or failed: what the tab showed before the devices were loaded
                self._show_tab(self.device_tabs.active)
            return
        name = self.ui_session.session.selected_device if restore else None
        if name is not None and any(device.name == name for device in devices):
            self.on_device_selected(name)
        else:
            self._show_no_device_selected()

    def _on_devices_failed(self, ex: Exception):
        self._set_load_error(None, ex)
        self.device_list_widget.show_error()
        self.message_panel.show_error(
            title="Could not load the config directory",
            error=f"{self.config_manager.cfg_root}\n\n{error_text(ex)}",
            retry=self.load_plates,
        )
        self.center_stack.setCurrentWidget(self.message_panel)

    def _set_devices(self, devices: List[Device]):
        self.devices = devices
        self._state_publisher.request()
        self.device_list_widget.set_devices(self.devices, selected=self._selected_name)

    @property
    def device(self) -> Optional[Device]:
        """The device of the active tab, None while it loads or if it couldn't be loaded."""
        tab = self.device_tabs.active
        return None if tab is None else tab.device

    @property
    def _selected_name(self) -> Optional[str]:
        """The name of the device of the active tab."""
        tab = self.device_tabs.active
        return None if tab is None else tab.name

    def _show_no_device_selected(self):
        self.message_panel.show_message(
            icon="gesture-tap",
            title="Select a device",
            text="Choose a plate from the list on the left to preview and edit its pages.",
        )
        self.center_stack.setCurrentWidget(self.message_panel)

    def on_device_selected(self, name: str):
        """
        Focus the tab of the device, or open one and load the pages of the device in the background. The device of the active
        tab is loaded again (to reflect any changes on disk).
        """
        tab = self.device_tabs.find(name)
        if tab is not None and tab is not self.device_tabs.active:
            self.device_tabs.activate(tab)
            return
        if tab is None:
            tab = self.device_tabs.open(name)
            # a new tab starts in interaction mode, not editing its objects by accident
            tab.editor.set_edit_mode(False)
        self._load_device(name)

    def _load_device(self, name: str):
        """Load the pages of a device in the background for its tabs, showing that it loads."""
        generation = self._load_generations[name] = self._load_generations.get(name, 0) + 1
        for tab in self.device_tabs.of_device(name):
            # the editors keep their page and zoom (hidden meanwhile), to go on with them
            tab.device = None
            tab.loaded = None
            tab.editor.device_controls.set_device(None)
            tab.message = lambda panel: panel.show_loading(f"Loading {name}…", "Rendering the templates of the device's pages")
        if self._selected_name == name:
            self._show_tab(self.device_tabs.active)

        def __current() -> bool:
            # not if the tabs of the device were closed or it loads again in the meantime
            return bool(self.device_tabs.of_device(name)) and generation == self._load_generations[name]

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            if not __current():
                return
            self._set_devices(loaded.devices)
            try:
                self.select_device(loaded)
            except Exception as ex:
                LOGGER.exception(f"Could not load {name}")
                __on_error(ex)

        def __on_error(ex: Exception):
            if not __current():
                return
            self._set_load_error(name, ex)
            for tab in self.device_tabs.of_device(name):
                tab.message = lambda panel: panel.show_error(
                    title=f"Could not load {name}",
                    error=error_text(ex),
                    retry=lambda: self._load_device(name),
                )
            if self._selected_name == name:
                self._show_tab(self.device_tabs.active)

        run_async(__load(), on_success=__on_success, on_error=__on_error)

    # --- tabs ---

    def _on_tab_opened(self, tab: DeviceTab):
        """The connection to the plate of the device and its `PlateLink`, shared by its tabs, until the last of them closes."""
        self.connections.open(tab.name, tab)
        link = self.connections.link(tab.name)
        tab.editor.set_plate(link)
        if link.view is None:
            link.set_view(tab.editor)
        self._update_plates()

    def _on_tab_activated(self, tab: Optional[DeviceTab], previous: Optional[DeviceTab]):
        """
        Another tab is the active one: the panels, the status bar and the log follow it, nothing is loaded again. The
        connection and Live preview of the previous one keep running.
        """
        if previous is not None:
            previous.editor.device_controls.set_device(None)
            if not self.disk_changes_banner.isHidden():
                # offered again when the tab is shown again
                previous.changed_files |= {self.cfg_root / path for path in self.disk_changes}
        self.disk_changes_banner.hide()
        self._show_editor(self.page_layout_editor_widget)
        # edits through other tabs can change what Undo and Redo do here
        self.page_layout_editor_widget.update_undo_actions()
        if tab is not None:
            # the plate shows the page of the tab of its device that was active last
            self.connections.link(tab.name).set_view(tab.editor)
        self._show_tab(tab)
        if tab is not None and tab.device is not None and tab.changed_files:
            changed, tab.changed_files = tab.changed_files, set()
            self._apply_changes_to_draft(changed)

    def _show_tab(self, tab: Optional[DeviceTab]):
        """Point the panels at the device of a tab: the Files tree, the status bar, the Plates panel, the log."""
        editor = self.page_layout_editor_widget
        device = None if tab is None else tab.device
        self.status_bar.set_connection(self.connection.status)
        self._update_plates()
        self.device_logs.show(None if tab is None else tab.name)
        editor.device_controls.set_device(device)
        self.status_bar.set_device(None if tab is None else tab.name)
        if device is None:
            self.file_tree_widget.clear()
            self.status_bar.set_page(None)
            self.status_bar.set_dirty(False)
            if tab is None:
                self._show_no_device_selected()
            else:
                if tab.message is not None:
                    tab.message(self.message_panel)
                self.center_stack.setCurrentWidget(self.message_panel)
        else:
            loaded = tab.loaded
            self.file_tree_widget.set_files(
                loaded.files,
                components={component.path: component.key for component in loaded.components},
                used=loaded.used_files,
                used_variables=loaded.used_variable_files,
                includers=loaded.includers,
                common_path=Path(self.config_manager.cfg_root, COMMON_FOLDER_NAME),
            )
            self._update_file_tree_state()
            self.source_editor.set_hints(loaded.unused_variables)
            self.source_sync.set_variable_usages(loaded.variable_usages)
            self.status_bar.set_page(editor.current_index, len(get_navigable_page_indices(editor.working_objects)))
            self.status_bar.set_dirty(editor.is_dirty)
            self.center_stack.setCurrentWidget(editor)
        self.ui_session.session.selected_device = None if tab is None else tab.name
        self.ui_session.save()
        self.device_list_widget.set_devices(self.devices, selected=self._selected_name)
        self._update_draft_actions()
        self._state_publisher.request()

    def close_tab(self, tab: DeviceTab) -> bool:
        """
        Close a tab. The drafts stay (`sessions`), except the one of a part on its own, which asks to be saved first. With
        the last tab of a device its connection, Live preview and log end.
        :return: whether it was closed
        """
        if isinstance(tab, PartTab) and tab.alone and tab.focus.session.is_dirty:
            self.device_tabs.activate(tab)
            if not self._ask_to_save_part_alone(tab):
                return False
        others = [other for other in self.device_tabs.of_device(tab.name) if other is not tab]
        link = self.connections.link(tab.name)
        if link.view is tab.editor:
            # the plate goes on with the page of another tab of the device
            link.set_view(others[0].editor if others else None)
        if isinstance(tab, PartTab):
            tab.focus.close()
        tab.editor.device_controls.set_device(None)
        tab.editor.clear()
        tab.editor.set_plate(None)
        if not others:
            self.device_logs.drop(tab.name)
        editor = self.device_tabs.close(tab)
        if editor is not None:
            self._delete_editor(editor)
        self.connections.close(tab.name, tab)
        self._update_plates()
        return True

    def _ask_to_save_part_alone(self, tab: PartTab) -> bool:
        """
        The draft of a part on its own goes away with its tab: save its changes first?
        :return: whether the tab can be closed (not if the user cancelled, or the save failed)
        """
        answer = QMessageBox.question(
            self,
            "Unsaved part",
            f"Save the changes of {tab.part.name}? Its draft goes away with its tab.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return answer != QMessageBox.StandardButton.Save or self.draft_actions.save(tab.focus.session)

    # --- plates ---

    def _on_connection_changed(self, name: str, status: ConnectionStatus):
        """The connection to the plate of an open device changed: its tabs, the Plates panel and the status bar show it."""
        for tab in self.device_tabs.of_device(name):
            self.device_tabs.set_connection(tab, status)
        if status.link == LinkState.PLATE_OFFLINE:
            # a plate that went offline (e.g. restarted) shows its files again, not what Live preview sent
            self.connections.link(name).forget_sent()
        if self._selected_name == name:
            self.status_bar.set_connection(status)
            self._state_publisher.request()
        self._update_plates()

    def _on_live_changed(self, name: str):
        for tab in self.device_tabs.of_device(name):
            self.device_tabs.update_title(tab)
        self._update_plates()

    def _live_preview_refusal(self, name: str) -> Optional[str]:
        """:return: why Live preview can't be turned on for a device, None if it can"""
        others = {other for other in self.connections.names if other != name and self.connections.link(other).live}
        return live_preview_refusal(name, sorted(others))

    def set_live_preview(self, name: str, on: bool):
        """Turn Live preview of an open device on or off (e.g. in the Plates panel), as its action in the toolbar does."""
        action = self.connections.link(name).action_live_preview
        if action.isEnabled():
            action.setChecked(on)
        # also if it was refused, or the device isn't loaded yet: the panel shows how it is
        self._update_plates()

    def _update_plates(self):
        rows = [
            PlateRow(
                device=name,
                connection=self.connections.get(name).status,
                live=self.connections.link(name).live,
            )
            for name in self.connections.names
        ]
        self.plates_panel.set_rows(rows, active=self._selected_name)

    def _update_tab_title(self, tab: Optional[DeviceTab]):
        """The title of a tab marks unsaved changes of the files it shows (of a part tab: see `PartFocus.undo_scope`)."""
        if tab is not None:
            self.device_tabs.set_dirty(tab, tab.editor.is_dirty)

    # --- changes on disk ---

    def _start_watching_config_dir(self):
        """Reload when files in the config directory change, e.g. because an LLM or a text editor edits them."""
        output_root = Path(self.config_manager.output_root).resolve()
        self._watcher = ConfigWatcher(self.cfg_root, ignored_roots=[output_root], parent=self)
        self._watcher.changed.connect(self._on_config_changed)
        self._watcher.start()

    def _on_config_changed(self, paths: Set[Path]):
        """
        Files changed in the config directory. A draft without changes follows them. A draft with changes is never
        replaced: the user chooses in a banner (Save detects the same conflict too, but only when it is too late).
        """
        paths = self.own_writes.foreign(paths)
        if not paths:
            return
        LOGGER.info(f"Changed on disk: {', '.join(sorted(str(path) for path in paths))}")
        self.source_editor.external_changes(paths)
        self.mark_changed_in_background_tabs(paths)
        self._apply_changes_to_draft(paths)

    def reload_files(self, paths: Set[Path]):
        """Files changed by the app itself (e.g. a file operation of the Files tree): the pages and the files follow them."""
        paths = {path.resolve() for path in paths}
        self.mark_changed_in_background_tabs(paths)
        self._apply_changes_to_draft(paths)

    def mark_changed_in_background_tabs(self, paths: Set[Path]):
        """Files changed that the devices of tabs in the background may show: they follow them when they are shown again."""
        for tab in self.device_tabs.tabs:
            if tab is not self.device_tabs.active and tab.device is not None:
                tab.changed_files |= {path for path in paths if self._affects(tab.device, path)}

    def _affects(self, device: Device, path: Path) -> bool:
        """:return: whether a changed file can change the pages of a device: a file of it, or one outside of the devices"""
        return path.is_relative_to(device.path.resolve()) or not path.is_relative_to(self.cfg_root / DEVICES_FOLDER_NAME)

    def _apply_changes_to_draft(self, paths: Set[Path]):
        """Files changed that the pages are made of: reload them, or offer to if the draft has changes of its own."""
        if self._reloading_changes is not None:
            self._changes_during_reload |= paths
            return
        session = self.session
        if session is not None and session.is_dirty:
            self._show_disk_changes(paths)
        elif self._selected_name is None:
            self.load_plates()
        elif self.device is None:
            # still loading the device (or it failed): load again
            self._load_device(self._selected_name)
        else:
            self._reload_changed_files(paths)

    # --- text editor ---

    def _on_source_saved(self, path: Path, text: str):
        """A file was saved in the text editor: the pages follow it, like after a change on disk by someone else."""
        self.own_writes.written(path.resolve(), text)
        self.status.succeeded.emit(f"Saved {path.name}")
        self.mark_changed_in_background_tabs({path.resolve()})
        if self.device is not None:
            self._apply_changes_to_draft({path.resolve()})

    def _show_disk_changes(self, paths: Set[Path]):
        """Offer to reload, if the changes can affect the device of the draft."""
        affecting = sorted(path for path in paths if self._affects(self.device, path))
        if affecting:
            self.disk_changes = [str(path.relative_to(self.cfg_root)) for path in affecting]
            self.disk_changes_banner.show_message(
                f"Changed on disk since this draft was loaded: {file_list_text(self.disk_changes)}"
            )

    def _reload_changed_files(self, paths: Set[Path]):
        """Load the device again, in the background and without leaving the editor: the page and zoom stay."""
        tab = self.device_tabs.active
        name = tab.name
        self._reloading_changes = paths
        self._changes_during_reload = set()
        self._page_after_reload[self.session_key] = self.page_layout_editor_widget.current_index
        key = self.session_key
        generation = self._load_generations.get(name, 0)

        def __finish():
            more, self._reloading_changes, self._changes_during_reload = self._changes_during_reload, None, set()
            if more:
                self._on_config_changed(more)

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            changes = self._reloading_changes
            __finish()
            if tab not in self.device_tabs.tabs or generation != self._load_generations.get(name, 0) or tab.device is None:
                self._page_after_reload.pop(key, None)
                return  # closed or loaded again in the meantime
            if tab is not self.device_tabs.active:
                # another tab was chosen in the meantime: this one follows the files when it is shown again
                self._page_after_reload.pop(key, None)
                tab.changed_files |= changes
                return
            if self.session.is_dirty:
                # edited while loading: keep the draft
                self._page_after_reload.pop(key, None)
                self._show_disk_changes(changes)
                return
            self._set_devices(loaded.devices)
            try:
                self.select_device(loaded, keep_view=True, tab=tab)
            except Exception as ex:
                LOGGER.exception(f"Could not reload {name}")
                __show_error(ex)
                return
            names = sorted(str(path.relative_to(self.cfg_root)) for path in changes)
            self.status.succeeded.emit(f"Reloaded {name}, changed on disk: {', '.join(names[:3])}")

        def __on_error(ex: Exception):
            __finish()
            __show_error(ex)

        def __show_error(ex: Exception):
            # e.g. a file that is half written: stay with what is shown, the next change loads again
            self._page_after_reload.pop(key, None)
            self._set_load_error(name, ex)
            self.status.failed.emit(f"Reloading {name} after a change on disk", error_text(ex))

        run_async(__load(), on_success=__on_success, on_error=__on_error)

    # --- state file ---

    def _on_operation(self, ok: bool, message: str):
        self.last_operation = {"ok": ok, "message": message, "time": now()}
        self._state_publisher.request()

    def _set_load_error(self, device: Optional[str], ex: Exception):
        self.load_error = {"device": device, "message": error_text(ex), "time": now()}
        self._state_publisher.request()

    # --- draft ---

    @property
    def session(self) -> Optional[PlateSession]:
        """
        The draft in the active tab: of the pages of the device, also in a part tab, or of a part on its own (see
        `edit_part`).
        """
        tab = self.device_tabs.active
        if tab is None or tab.device is None:
            return None
        if isinstance(tab, PartTab):
            return tab.focus.session
        return self.sessions.get(tab.session_key)

    @property
    def session_key(self) -> Optional[Tuple[str, str]]:
        """The (device name, cmd component) of the draft of the pages of the device of the active tab."""
        tab = self.device_tabs.active
        return None if tab is None else tab.session_key

    def _update_draft_actions(self):
        session = self.session
        dirty = session is not None and session.is_dirty
        # Save writes every changed file (see `DraftActions.save`), also those of other tabs
        self.action_save.setEnabled(
            dirty or (session is not None and not session.is_part_alone and bool(self.config_draft.dirty_paths))
        )
        self.action_revert.setEnabled(dirty)

    def shown_keys(self, session: PlateSession) -> Set[str]:
        """
        :return: the keys of the files and parts that the tab of a draft shows: those of its device, or for the active part
            tab, its part and the files that include its instance (see `PartFocus.undo_scope`)
        """
        tab = self.device_tabs.active
        if isinstance(tab, PartTab) and not tab.alone and tab.focus.session is session:
            return set(tab.focus.undo_scope)
        return set(session.file_keys) | set(session.part_keys)
        self.action_deploy.setEnabled(self.device is not None and not self.page_layout_editor_widget.busy.busy)

    def reload_draft(self):
        """Drop the draft of the active tab (or of the part on its own) and load it from disk, on the same page."""
        tab = self.device_tabs.active
        self.disk_changes_banner.hide()
        if isinstance(tab, PartTab) and tab.alone:
            self._reload_part_alone(tab)
            return
        # its files (also those other devices show) are as on disk afterwards
        self.sessions.pop(tab.session_key).discard()
        self._page_after_reload[tab.session_key] = tab.editor.current_index
        self._load_device(tab.name)

    def select_device(self, loaded: LoadedDevice, keep_view: bool = False, tab: Optional[DeviceTab] = None):
        """
        Show a loaded device in its tabs (of its pages, and of its parts). Raises if the pages can't be rendered, before
        anything changed.

        :param keep_view: the same device is loaded again: don't change the zoom
        :param tab: the tab the device was loaded for, which shows the page after a reload (see `_page_after_reload`); the
            active one by default
        """
        tab = tab or self.device_tabs.active
        pages_data = OpenHaspDevicePagesData(
            device=loaded.device,
            name=loaded.cmd_component.name,
            jsonl_components=loaded.jsonl_components,
            part_includers=loaded.part_includers,
        )
        key = (loaded.device.name, pages_data.name)
        session = self.sessions.get(key) or PlateSession(device=loaded.device, config=self.config_draft)
        # a draft without changes follows the files on disk, one with changes is kept (Save detects conflicts)
        if not session.is_loaded or not session.is_dirty:
            session.load(loaded.components, loaded.renderer)
        session.device = loaded.device
        self.sessions[key] = session
        self.load_error = None
        # each open device keeps its log and its connection, also in the background
        self.device_logs.log_of(loaded.device.name).stream.set_device(loaded.device)
        self.connections.get(loaded.device.name).set_device(loaded.device)
        page_after_reload = self._page_after_reload.pop(key, None)
        for shown in self.device_tabs.of_device(loaded.device.name):
            editor = shown.editor
            # a new tab, which has no page to go on with
            fresh = editor.session is None
            page = None if fresh else editor.current_index
            shown.device = loaded.device
            shown.loaded = loaded
            shown.message = None
            shown.session_key = key
            shown.pages_data = pages_data
            # the tab shows the files as they are now
            shown.changed_files = set()
            if isinstance(shown, PartTab):
                if not self._show_part_tab(shown, session, page=page):
                    continue
            else:
                if shown is tab and page_after_reload is not None:
                    page = page_after_reload
                editor.set_data(session=session, device_pages_data=pages_data, page=page)
            self._update_tab_title(shown)
            if (shown is tab or fresh) and not keep_view:
                editor.page_preview_widget.fit_to_view()
        if self.device_tabs.active is not None and self.device_tabs.active.name == loaded.device.name:
            self._show_tab(self.device_tabs.active)

    # --- part tabs ---

    def edit_part(self, part: Path, instance: Optional[PartInstance] = None, session: Optional[PlateSession] = None):
        """
        "Edit the part": open a part tab for a part of the device of the active tab, or focus the one that is open. It shows the
        part in an instance of the pages of the device (the first one by default), or on its own if no page includes it (see
        `load_part_alone`).

        :param instance: the instance to edit, of the draft `session` (one in another draft is not used)
        """
        tab = self.device_tabs.active
        if tab is None or tab.device is None:
            return
        name = tab.name
        pages = self.sessions[tab.session_key]
        part = part.resolve()
        if pages.component_at(part) is not None:
            self.status.failed.emit(
                f"Editing the part {part.name}", "it is a page file of the device: edit its objects on the page"
            )
            return
        instances = pages.part_instances(part)
        if session is not pages or instance not in instances:
            instance = None
        existing = self.device_tabs.find_part(name, part)
        if existing is not None:
            if instance is not None and not existing.alone and existing.focus.instance != instance:
                existing.focus.move_to(instance)
                existing.editor.set_data(session=pages, device_pages_data=existing.pages_data, focus=existing.focus)
            self.device_tabs.activate(existing)
            return
        try:
            if instances:
                focus = PartFocus(pages, instance or instances[0])
            else:
                alone = self._load_part_alone(tab.device, part)
                if alone is None:
                    return
                focus = PartFocus(alone, alone.part_instances(part)[0])
        except ValueError as ex:
            self.status.failed.emit(f"Editing the part {part.name}", str(ex))
            return
        opened = self.device_tabs.open_part(name, part, focus)
        # what was loaded of the device is shared by its tabs
        opened.device, opened.loaded, opened.pages_data, opened.session_key = (
            tab.device,
            tab.loaded,
            tab.pages_data,
            tab.session_key,
        )
        opened.editor.set_show_page(False)
        opened.editor.set_data(session=focus.session, device_pages_data=tab.pages_data, focus=focus)
        # a part tab is for editing the part
        opened.editor.set_edit_mode(True)
        self._update_tab_title(opened)
        self.device_tabs.activate(opened)

    def _show_part_tab(self, tab: PartTab, session: PlateSession, page: Optional[int]) -> bool:
        """
        Show a part tab again after its device was loaded (again). The part goes on in the instance at the same place, or
        in its first one; a part on its own without changes follows its file on disk. A part that isn't included anymore
        closes its tab.
        :return: whether the tab is still open
        """
        focus = tab.focus
        if tab.alone:
            if not focus.session.is_dirty:
                self._reload_part_alone(tab, show=False)
            focus = tab.focus
            focus.session.device = tab.device
        elif focus.session is not session or not focus.is_active:
            # the draft was loaded anew (reverted), or doesn't include the instance anymore
            description = focus.describe() if focus.session is not session and focus.is_active else None
            instances = session.part_instances(tab.part)
            instance = next((i for i in instances if session.describe_instance(i) == description), None)
            instance = instance or next(iter(instances), None)
            if instance is None:
                self.status.failed.emit(f"Editing the part {tab.part.name}", "no page of the device includes it anymore")
                self.close_tab(tab)
                return False
            focus.close()
            focus = tab.focus = PartFocus(session, instance)
        tab.editor.set_data(session=focus.session, device_pages_data=tab.pages_data, page=page, focus=focus)
        return True

    def _load_part_alone(self, device: Device, part: Path) -> Optional[PlateSession]:
        """:return: a draft of the part on its own; None if it can't be loaded (which is reported)"""
        try:
            component, renderer = load_part_alone(self.config_manager, device, part)
            session = PlateSession(device=device)
            session.load([component], renderer)
            instances = session.part_instances(part)
            if not instances:
                raise ValueError("it has no objects to show")
        except Exception as ex:
            LOGGER.exception(f"Could not show {part} on its own")
            self.status.failed.emit(f"Editing the part {part.name}", error_text(ex))
            return None
        return session

    def _reload_part_alone(self, tab: PartTab, show: bool = True):
        """Load the part of a part tab on its own again from disk (its changes are discarded)."""
        alone = self._load_part_alone(tab.device, tab.part)
        if alone is None:
            return
        tab.focus.close()
        tab.focus = PartFocus(alone, alone.part_instances(tab.part)[0])
        if show:
            tab.editor.set_data(session=alone, device_pages_data=tab.pages_data, focus=tab.focus)
            self._update_tab_title(tab)
            self._update_draft_actions()


def create_application_settings():
    """QSettings() without arguments uses these names."""
    QtCore.QCoreApplication.setOrganizationName("openhasp-config-manager")
    QtCore.QCoreApplication.setApplicationName("openhasp-config-manager")
