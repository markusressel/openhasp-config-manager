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
from openhasp_config_manager.gui.domain.connection import LinkState
from openhasp_config_manager.gui.domain.gui_state import (
    GuiStateFile,
    now,
)
from openhasp_config_manager.gui.domain.draft.config_draft import ConfigDraft
from openhasp_config_manager.gui.domain.draft.page_objects import get_navigable_page_indices
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.components import ThemedIcons
from openhasp_config_manager.gui.qt.config_watcher import ConfigWatcher
from openhasp_config_manager.gui.qt.preview_image import png_bytes, render_plate
from openhasp_config_manager.gui.qt.window.gui_state_publisher import GuiStatePublisher
from openhasp_config_manager.gui.qt.window.device_logs import DeviceLogs
from openhasp_config_manager.gui.qt.window.device_tabs import DeviceTab, DeviceTabs
from openhasp_config_manager.gui.qt.window.draft_actions import DraftActions
from openhasp_config_manager.gui.qt.window.file_actions import FileActions
from openhasp_config_manager.gui.qt.window.gui_state_collector import collect_gui_state
from openhasp_config_manager.gui.qt.window.log_colors import LogColors
from openhasp_config_manager.gui.qt.window.menus import create_menus, show_editor_actions
from openhasp_config_manager.gui.qt.window.source_sync import SourceEditorSync
from openhasp_config_manager.gui.qt.window.status_bar import StatusBarController
from openhasp_config_manager.gui.qt.connection import ConnectionController
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
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
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
        self.file_tree_widget.editPartRequested.connect(lambda part: self.page_layout_editor_widget.edit_part(part))
        self.source_editor.set_part_check(self.file_tree_widget.is_part_file)
        self.source_editor.editPartRequested.connect(lambda part: self.page_layout_editor_widget.edit_part(part))
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
        self._size_docks()

        self.status_bar = StatusBarController(
            self, self.status, on_resync=lambda index: self.page_layout_editor_widget.resync_page(index)
        )

        # the connection to the plate of the active tab
        self.connection = ConnectionController(self)
        self.connection.changed.connect(self.status_bar.set_connection)
        self.connection.changed.connect(lambda _: self._state_publisher.request())
        # a plate that went offline (e.g. restarted) shows its files again, not what Live preview sent
        self.connection.changed.connect(
            lambda status: (
                self.page_layout_editor_widget.plate.forget_sent() if status.link == LinkState.PLATE_OFFLINE else None
            )
        )
        self.status_bar.set_connection(self.connection.status)

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
        editor.editPartAloneRequested.connect(active(self.edit_part_alone))
        editor.partAloneDone.connect(active(self.close_part_alone))
        editor.action_edit_mode.toggled.connect(active(self._on_edit_mode_toggled))
        editor.plate.pageOutOfSync.connect(active(lambda *args: self.connection.page_out_of_sync(*args)))
        editor.plate.pageDeployed.connect(active(lambda *args: self.connection.page_deployed(*args)))
        editor.plate.plateRestored.connect(active(lambda *args: self.connection.plate_restored(*args)))
        for busy in [editor.busy, editor.device_controls.busy]:
            busy.changed.connect(active(lambda _: self._update_sending()))
            busy.changed.connect(active(lambda _: self._update_draft_actions()))
        self.center_stack.addWidget(editor)
        self.properties_stack.addWidget(editor.property_editor)
        self.page_jsonl_stack.addWidget(editor.jsonl_preview)
        return editor

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
        self._update_sending()

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

    def _update_sending(self):
        self.connection.set_sending(
            self.page_layout_editor_widget.busy.busy or self.page_layout_editor_widget.device_controls.busy.busy
        )

    def set_theme(self, mode: ThemeMode):
        apply_theme(mode)
        ThemedIcons.refresh()
        self.status_bar.refresh_theme()
        self.file_tree_widget.refresh_theme()
        self.file_rendered.view.refresh_theme()
        self.source_editor.refresh_theme()
        self.device_logs.refresh_theme()
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
            if tab.part_alone is not None and tab.part_alone.is_dirty:
                names.append(f"{tab.part_alone_path.name} (part)")
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
        self.connection.stop()
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
        self._load_device(tab)

    def _load_device(self, tab: DeviceTab):
        """Load the pages of the device of a tab in the background, showing that it loads."""
        name = tab.name
        tab.device = None
        tab.loaded = None
        tab.load_generation += 1
        generation = tab.load_generation
        tab.editor.device_controls.set_device(None)
        tab.editor.clear()
        tab.message = lambda panel: panel.show_loading(f"Loading {name}…", "Rendering the templates of the device's pages")
        if tab is self.device_tabs.active:
            self._show_tab(tab, keep_connection=True)

        def __current() -> bool:
            # not if the tab was closed or loads again in the meantime
            return tab in self.device_tabs.tabs and generation == tab.load_generation

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            if not __current():
                return
            self._set_devices(loaded.devices)
            try:
                self.select_device(loaded, tab=tab)
            except Exception as ex:
                LOGGER.exception(f"Could not load {name}")
                __on_error(ex)

        def __on_error(ex: Exception):
            if not __current():
                return
            self._set_load_error(name, ex)
            tab.message = lambda panel: panel.show_error(
                title=f"Could not load {name}",
                error=error_text(ex),
                retry=lambda: self._load_device(tab),
            )
            if tab is self.device_tabs.active:
                self._show_tab(tab, keep_connection=True)

        run_async(__load(), on_success=__on_success, on_error=__on_error)

    # --- tabs ---

    def _on_tab_activated(self, tab: Optional[DeviceTab], previous: Optional[DeviceTab]):
        """Another tab is the active one: the panels, the connection and the log follow it, nothing is loaded again."""
        if previous is not None:
            # like selecting another device: Live preview and the connection stay with the active tab (for now)
            previous.editor.plate.stop_live_preview()
            previous.editor.device_controls.set_device(None)
            if not self.disk_changes_banner.isHidden():
                # offered again when the tab is shown again
                previous.changed_files |= {self.cfg_root / path for path in self.disk_changes}
        self.disk_changes_banner.hide()
        self._show_editor(self.page_layout_editor_widget)
        self._show_tab(tab)
        if tab is not None and tab.device is not None and tab.changed_files:
            changed, tab.changed_files = tab.changed_files, set()
            self._apply_changes_to_draft(changed)

    def _show_tab(self, tab: Optional[DeviceTab], keep_connection: bool = False):
        """
        Point the panels at the device of a tab: the Files tree, the status bar, the connection, the log.
        :param keep_connection: the device of the tab loads again: the connection and the log stay while it loads
        """
        editor = self.page_layout_editor_widget
        device = None if tab is None else tab.device
        if device is not None or not keep_connection:
            self.connection.set_device(device)
        self.device_logs.show(tab)
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
            self.status_bar.set_dirty(self.session.is_dirty)
            self.center_stack.setCurrentWidget(editor)
        self.ui_session.session.selected_device = None if tab is None else tab.name
        self.ui_session.save()
        self.device_list_widget.set_devices(self.devices, selected=self._selected_name)
        self._update_draft_actions()
        self._state_publisher.request()

    def close_tab(self, tab: DeviceTab) -> bool:
        """
        Close the tab of a device. Its drafts stay (`sessions`), except a part on its own, which asks to be saved first.
        :return: whether it was closed
        """
        if tab.part_alone is not None:
            self.device_tabs.activate(tab)
            if not self.close_part_alone():
                return False
        tab.editor.plate.stop_live_preview()
        tab.editor.device_controls.set_device(None)
        tab.editor.clear()
        self.device_logs.drop(tab)
        editor = self.device_tabs.close(tab)
        if editor is not None:
            self._delete_editor(editor)
        return True

    def _update_tab_title(self, tab: Optional[DeviceTab]):
        """The title of a tab marks unsaved changes of its drafts."""
        if tab is None:
            return
        session = self.sessions.get(tab.session_key)
        dirty = (session is not None and session.is_dirty) or (tab.part_alone is not None and tab.part_alone.is_dirty)
        self.device_tabs.set_dirty(tab, dirty)

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
            self.on_device_selected(self._selected_name)
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
        generation = tab.load_generation

        def __finish():
            more, self._reloading_changes, self._changes_during_reload = self._changes_during_reload, None, set()
            if more:
                self._on_config_changed(more)

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            changes = self._reloading_changes
            __finish()
            if tab not in self.device_tabs.tabs or generation != tab.load_generation or tab.device is None:
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
        """The draft in the active tab: of the pages of the device, or of a part on its own (see `edit_part_alone`)."""
        tab = self.device_tabs.active
        if tab is None or tab.device is None:
            return None
        return tab.part_alone or self.sessions.get(tab.session_key)

    @property
    def session_key(self) -> Optional[Tuple[str, str]]:
        """The (device name, cmd component) of the draft of the pages in the active tab."""
        tab = self.device_tabs.active
        return None if tab is None else tab.session_key

    @property
    def part_alone(self) -> Optional[PlateSession]:
        """The draft of a part on its own in the active tab, if it shows one (see `edit_part_alone`)."""
        tab = self.device_tabs.active
        return None if tab is None else tab.part_alone

    def _update_draft_actions(self):
        dirty = self.session is not None and self.session.is_dirty
        self.action_save.setEnabled(dirty)
        self.action_revert.setEnabled(dirty)
        self.action_deploy.setEnabled(self.device is not None and not self.page_layout_editor_widget.busy.busy)

    def reload_draft(self):
        """Drop the draft of the active tab (or of the part on its own) and load it from disk, on the same page."""
        tab = self.device_tabs.active
        self.disk_changes_banner.hide()
        if tab.part_alone is not None:
            alone = self._load_part_alone(tab, tab.part_alone_path)
            if alone is not None:
                self._show_part_alone(tab, alone)
            return
        # its files (also those other devices show) are as on disk afterwards
        self.sessions.pop(tab.session_key).discard()
        self._page_after_reload[tab.session_key] = tab.editor.current_index
        self._load_device(tab)

    def select_device(self, loaded: LoadedDevice, keep_view: bool = False, tab: Optional[DeviceTab] = None):
        """
        Show a loaded device in its tab. Raises if the pages can't be rendered, before anything changed.

        :param keep_view: the same device is loaded again: don't change the zoom
        :param tab: the tab of the device, the active one by default
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
        tab.device = loaded.device
        tab.loaded = loaded
        tab.message = None
        self.load_error = None
        tab.session_key = key
        tab.pages_data = pages_data
        # each open device keeps its log, also in the background
        self.device_logs.log_of(tab).stream.set_device(loaded.device)
        if tab.part_alone is not None:
            # a part on its own without changes follows the files on disk too, if it is still a file of the device
            alone = tab.part_alone
            if not alone.is_dirty:
                alone = self._load_part_alone(tab, tab.part_alone_path)
            if alone is not None:
                alone.device = loaded.device
            tab.part_alone = alone
        editor = tab.editor
        if tab.part_alone is not None:
            self._page_after_reload.pop(key, None)
            self._show_part_alone(tab, tab.part_alone)
        else:
            editor.set_data(session=session, device_pages_data=pages_data, page=self._page_after_reload.pop(key, None))
        if tab is self.device_tabs.active:
            self._show_tab(tab)
        self._update_tab_title(tab)
        if not keep_view:
            editor.page_preview_widget.fit_to_view()

    # --- a part on its own ---

    def edit_part_alone(self, part: Path):
        """
        Part mode for a part that no page of the device includes: the editor of the active tab shows the part on its own
        instead of the pages (see `load_part_alone`), until "Done".
        """
        tab = self.device_tabs.active
        if tab is None or tab.device is None:
            return
        if part.resolve() in {component.path.resolve() for component in self.sessions[tab.session_key].components}:
            self.status.failed.emit(
                f"Editing the part {part.name}", "it is a page file of the device: edit its objects on the page"
            )
            return
        if self.sessions[tab.session_key].part_instances(part):
            # asked for while another part is shown on its own: this one is edited on the pages
            if self.close_part_alone():
                tab.editor.edit_part(part)
            return
        if tab.part_alone is not None and not self.close_part_alone():
            return
        alone = self._load_part_alone(tab, part)
        if alone is None:
            return
        tab.page_before_part_alone = tab.editor.current_index
        tab.part_alone_path = part
        self._show_part_alone(tab, alone)

    def _load_part_alone(self, tab: DeviceTab, part: Path) -> Optional[PlateSession]:
        """:return: a draft of the part on its own (shown in part mode); None if it can't be loaded (which is reported)"""
        try:
            component, renderer = load_part_alone(self.config_manager, tab.device, part)
            session = PlateSession(device=tab.device)
            session.load([component], renderer)
            instances = session.part_instances(part)
            if not instances:
                raise ValueError("it has no objects to show")
        except Exception as ex:
            LOGGER.exception(f"Could not show {part} on its own")
            self.status.failed.emit(f"Editing the part {part.name}", error_text(ex))
            return None
        return session

    def _show_part_alone(self, tab: DeviceTab, alone: PlateSession):
        tab.part_alone = alone
        editor = tab.editor
        # in part mode of its first instance, unless the editor shows the part already (e.g. it was loaded again)
        mode = editor.part_mode if editor.session is alone else None
        instance = mode or alone.part_instances(tab.part_alone_path)[0]
        editor.set_data(session=alone, device_pages_data=tab.pages_data, page=alone.page_of_instance(instance), part=instance)
        if not editor.edit_mode:
            editor.set_edit_mode(True)
        self._update_draft_actions()
        self._update_tab_title(tab)
        self._state_publisher.request()

    def close_part_alone(self) -> bool:
        """
        Back from a part on its own to the pages of the device in the active tab. Asks to save the part first if it has changes.
        :return: whether it was closed (not if the user cancelled, or the save failed)
        """
        tab = self.device_tabs.active
        alone = None if tab is None else tab.part_alone
        if alone is None:
            return True
        if alone.is_dirty:
            answer = QMessageBox.question(
                self,
                "Unsaved part",
                f"Save the changes of {tab.part_alone_path.name}? Its draft goes away with the part.",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save and not self.draft_actions.save():
                return False
        tab.part_alone = None
        tab.part_alone_path = None
        session = self.sessions.get(tab.session_key)
        if session is not None and tab.pages_data is not None:
            tab.editor.set_data(session=session, device_pages_data=tab.pages_data, page=tab.page_before_part_alone)
        self._update_draft_actions()
        self._update_tab_title(tab)
        self._state_publisher.request()
        return True


def create_application_settings():
    """QSettings() without arguments uses these names."""
    QtCore.QCoreApplication.setOrganizationName("openhasp-config-manager")
    QtCore.QCoreApplication.setApplicationName("openhasp-config-manager")
