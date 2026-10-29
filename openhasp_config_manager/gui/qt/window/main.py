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
)
from openhasp_config_manager.gui.domain.config_changes import OwnWrites
from openhasp_config_manager.gui.domain.gui_state import (
    GuiStateFile,
    now,
)
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.components import ThemedIcons
from openhasp_config_manager.gui.qt.config_watcher import ConfigWatcher
from openhasp_config_manager.gui.qt.window.gui_state_publisher import GuiStatePublisher
from openhasp_config_manager.gui.qt.window.draft_actions import DraftActions
from openhasp_config_manager.gui.qt.window.gui_state_collector import collect_gui_state
from openhasp_config_manager.gui.qt.window.log_colors import LogColors
from openhasp_config_manager.gui.qt.window.menus import create_menus
from openhasp_config_manager.gui.qt.window.source_sync import SourceEditorSync
from openhasp_config_manager.gui.qt.window.status_bar import StatusBarController
from openhasp_config_manager.gui.qt.connection import ConnectionController
from openhasp_config_manager.gui.qt.log_stream import LogStreamController
from openhasp_config_manager.gui.qt.operations import OperationStatus, error_text
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.theme import ThemeMode, apply_theme
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.widgets.source.code_view import CodeView
from openhasp_config_manager.gui.qt.widgets.source.rendered_view import FileRenderedView
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.source.file_tree import FileTreeWidget
from openhasp_config_manager.gui.qt.widgets.log_view import LogView
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
        # one draft per (device name, cmd component): the Device objects are created anew on every reload
        self.sessions: Dict[Tuple[str, str], PlateSession] = {}
        self.device: Optional[Device] = None
        self._selected_name: Optional[str] = None
        # the (device name, cmd component) of the draft in the editor
        self.session_key: Optional[Tuple[str, str]] = None
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
            GuiStateFile(self.cfg_root), lambda running=True: collect_gui_state(self, running), parent=self
        )

        self.setWindowTitle("openhasp-config-manager")
        self.setMinimumSize(960, 600)
        self.setDockNestingEnabled(True)

        self.create_basic_layout()
        self.draft_actions = DraftActions(self)
        create_menus(self)
        self._update_draft_actions()
        # the arrangement of the docks as built above, before the saved one is restored
        self._default_dock_state = self.saveState(DOCK_STATE_VERSION)
        self._restore_window_state()
        # the editor starts in interact mode, which has nothing to show in the properties
        self.properties_dock.hide()
        self.page_layout_editor_widget.action_edit_mode.toggled.connect(self._on_edit_mode_toggled)
        self.load_plates()
        self._start_watching_config_dir()
        self.source_sync.restore_open_files()
        self._state_publisher.request()

    # --- layout ---

    def create_basic_layout(self):
        self.page_layout_editor_widget = PageLayoutEditorWidget(status=self.status, ui_session=self.ui_session)
        self.page_layout_editor_widget.pageChanged.connect(lambda index, count: self.status_bar.set_page(index, count))
        self.page_layout_editor_widget.dirtyChanged.connect(lambda dirty: self.status_bar.set_dirty(dirty))
        self.page_layout_editor_widget.dirtyChanged.connect(lambda _: self._update_draft_actions())
        self.page_layout_editor_widget.stateChanged.connect(self._state_publisher.request)
        self.page_layout_editor_widget.dirtyChanged.connect(lambda _: self._state_publisher.request())
        self.page_layout_editor_widget.pageChanged.connect(lambda *_: self._state_publisher.request())
        self.addToolBar(self.page_layout_editor_widget.toolbar)

        # all panels are docks, so each can be moved: the central widget is only there for Qt
        central = QWidget()
        central.hide()
        self.setCentralWidget(central)

        # a placeholder (no device, loading, errors) or the editor with the render preview
        self.message_panel = MessagePanel()
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.message_panel)
        self.center_stack.addWidget(self.page_layout_editor_widget)
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
        center_layout.addWidget(self.disk_changes_banner)
        center_layout.addWidget(self.center_stack, 1)

        # left: devices and their files
        self.device_list_widget = DeviceListWidget()
        self.device_list_widget.deviceSelected.connect(self.on_device_selected)
        self.device_list_widget.reloadClicked.connect(self.load_plates)

        # the files of the selected device, and which of them new objects go into
        editor = self.page_layout_editor_widget
        self.file_tree_widget = FileTreeWidget()
        self.file_tree_widget.highlightRequested.connect(editor.highlight_component)
        self.file_tree_widget.targetRequested.connect(editor.set_target_component)
        editor.selectedObjectComponentChanged.connect(self.file_tree_widget.reveal)
        editor.fileStateChanged.connect(self._update_file_tree_state)

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
        self.properties_dock = self._add_dock("Properties", "properties_dock", self.page_layout_editor_widget.property_editor)
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
        self.jsonl_dock = self._add_dock("Code", "jsonl_dock", self.code_view)
        self.splitDockWidget(self.preview_dock, self.jsonl_dock, Qt.Orientation.Vertical)

        # the JSONL of the page in the preview: the objects of all files that contribute to it, the way the plate gets them
        self.page_jsonl_dock = self._add_dock("Page JSONL", "page_jsonl_dock", self.page_layout_editor_widget.jsonl_preview)
        self.tabifyDockWidget(self.jsonl_dock, self.page_jsonl_dock)

        # the log of the plate, next to the code. Hidden at first: it holds the only telnet connection the plate allows while shown.
        self.log_view = LogView()
        self.logs_dock = self._add_dock("Logs", "logs_dock", self.log_view)
        self.tabifyDockWidget(self.jsonl_dock, self.logs_dock)
        self.jsonl_dock.raise_()
        self.logs_dock.hide()
        self.log_stream = LogStreamController(self)
        self.log_stream.deviceChanged.connect(self.log_view.clear)
        self.log_stream.entriesReceived.connect(self.log_view.add_entries)
        self.log_stream.stateChanged.connect(lambda state, error: self.log_view.set_link(state, error))
        self.log_stream.colorsMissingChanged.connect(self.log_view.set_colors_missing)
        self.log_colors = LogColors(self)
        self.log_view.enableColorsRequested.connect(self.log_colors.ask)
        self.logs_dock.visibilityChanged.connect(self.log_stream.set_active)
        self._size_docks()

        self.status_bar = StatusBarController(self, self.status, on_resync=self.page_layout_editor_widget.resync_page)

        # the connection to the selected plate
        self.connection = ConnectionController(self)
        self.connection.changed.connect(self.status_bar.set_connection)
        self.connection.changed.connect(lambda _: self._state_publisher.request())
        self.status_bar.set_connection(self.connection.status)
        self.page_layout_editor_widget.plate.pageOutOfSync.connect(self.connection.page_out_of_sync)
        self.page_layout_editor_widget.plate.pageDeployed.connect(self.connection.page_deployed)
        self.page_layout_editor_widget.plate.plateRestored.connect(self.connection.plate_restored)
        for busy in [self.page_layout_editor_widget.busy, self.page_layout_editor_widget.device_controls.busy]:
            busy.changed.connect(lambda _: self._update_sending())
            busy.changed.connect(lambda _: self._update_draft_actions())

    def _on_edit_mode_toggled(self, enabled: bool):
        if enabled:
            self.properties_dock.show()

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
        self.page_layout_editor_widget.jsonl_preview.refresh_theme()
        self.file_rendered.view.refresh_theme()
        self.source_editor.refresh_theme()
        self.log_view.refresh_theme()
        self.page_layout_editor_widget.problems_panel.refresh_theme()
        self.page_layout_editor_widget.page_preview_widget.viewport().update()

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
        return [f"{device} ({cmd})" for (device, cmd), session in self.sessions.items() if session.is_dirty]

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
        self.log_stream.stop()
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
        if self.device is not None:
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

    def _show_no_device_selected(self):
        self.message_panel.show_message(
            icon="gesture-tap",
            title="Select a device",
            text="Choose a plate from the list on the left to preview and edit its pages.",
        )
        self.center_stack.setCurrentWidget(self.message_panel)

    def on_device_selected(self, name: str):
        """Reload the devices (to reflect any changes on disk) and load the pages of the selected one in the background."""
        self._selected_name = name
        self.ui_session.session.selected_device = name
        self.ui_session.save()
        if self.device is None or self.device.name != name:
            # another device: start without a connection and in interaction mode, not editing its objects by accident
            self.connection.set_device(None)
            self.log_stream.set_device(None)
            self.page_layout_editor_widget.set_edit_mode(False)
            self.page_layout_editor_widget.plate.stop_live_preview()
        self.device = None
        self.page_layout_editor_widget.device_controls.set_device(None)
        self.page_layout_editor_widget.clear()
        self.file_tree_widget.clear()
        self._update_draft_actions()
        self.status_bar.set_device(name)
        self.status_bar.set_page(None)
        self.status_bar.set_dirty(False)
        self._state_publisher.request()
        self.message_panel.show_loading(f"Loading {name}…", "Rendering the templates of the device's pages")
        self.center_stack.setCurrentWidget(self.message_panel)

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            if name != self._selected_name:
                return  # another device was selected in the meantime
            self._set_devices(loaded.devices)
            self.select_device(loaded)

        def __on_error(ex: Exception):
            if name != self._selected_name:
                return
            self._set_load_error(name, ex)
            self.message_panel.show_error(
                title=f"Could not load {name}",
                error=error_text(ex),
                retry=lambda: self.on_device_selected(name),
            )

        run_async(__load(), on_success=__on_success, on_error=__on_error)

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
        self._apply_changes_to_draft(paths)

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
        if self.device is not None:
            self._apply_changes_to_draft({path.resolve()})

    def _show_disk_changes(self, paths: Set[Path]):
        """Offer to reload, if the changes can affect the device of the draft."""
        devices_dir = self.cfg_root / DEVICES_FOLDER_NAME
        affecting = sorted(
            path for path in paths if path.is_relative_to(self.device.path.resolve()) or not path.is_relative_to(devices_dir)
        )
        if affecting:
            self.disk_changes = [str(path.relative_to(self.cfg_root)) for path in affecting]
            self.disk_changes_banner.show_message(
                f"Changed on disk since this draft was loaded: {file_list_text(self.disk_changes)}"
            )

    def _reload_changed_files(self, paths: Set[Path]):
        """Load the device again, in the background and without leaving the editor: the page and zoom stay."""
        name = self._selected_name
        self._reloading_changes = paths
        self._changes_during_reload = set()
        self._page_after_reload[self.session_key] = self.page_layout_editor_widget.current_index
        key = self.session_key

        def __finish():
            more, self._reloading_changes, self._changes_during_reload = self._changes_during_reload, None, set()
            if more:
                self._on_config_changed(more)

        async def __load():
            return await asyncio.to_thread(load_device, self.config_manager, name)

        def __on_success(loaded: LoadedDevice):
            changes = self._reloading_changes
            __finish()
            if name != self._selected_name or self.device is None:
                self._page_after_reload.pop(key, None)
                return  # another device was selected in the meantime
            if self.session.is_dirty:
                # edited while loading: keep the draft
                self._page_after_reload.pop(key, None)
                self._show_disk_changes(changes)
                return
            self._set_devices(loaded.devices)
            self.select_device(loaded, keep_view=True)
            names = sorted(str(path.relative_to(self.cfg_root)) for path in changes)
            self.status.succeeded.emit(f"Reloaded {name}, changed on disk: {', '.join(names[:3])}")

        def __on_error(ex: Exception):
            # e.g. a file that is half written: stay with what is shown, the next change loads again
            self._page_after_reload.pop(key, None)
            __finish()
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
        return None if self.device is None else self.sessions.get(self.session_key)

    def _update_draft_actions(self):
        dirty = self.session is not None and self.session.is_dirty
        self.action_save.setEnabled(dirty)
        self.action_revert.setEnabled(dirty)
        self.action_deploy.setEnabled(self.device is not None and not self.page_layout_editor_widget.busy.busy)

    def reload_draft(self):
        """Drop the draft of the current device and load it from disk, on the same page."""
        self.disk_changes_banner.hide()
        self.sessions.pop(self.session_key)
        self._page_after_reload[self.session_key] = self.page_layout_editor_widget.current_index
        self.on_device_selected(self.device.name)

    def select_device(self, loaded: LoadedDevice, keep_view: bool = False):
        """
        :param keep_view: the same device is loaded again: don't change the zoom
        """
        self.device = loaded.device
        self.load_error = None
        pages_data = OpenHaspDevicePagesData(
            device=loaded.device, name=loaded.cmd_component.name, jsonl_components=loaded.jsonl_components
        )
        key = (loaded.device.name, pages_data.name)
        session = self.sessions.setdefault(key, PlateSession(device=loaded.device))
        session.device = loaded.device
        # a draft without changes follows the files on disk, one with changes is kept (Save detects conflicts)
        if not session.is_loaded or not session.is_dirty:
            session.load(loaded.components, loaded.renderer)
        self.session_key = key
        self.file_tree_widget.set_files(
            loaded.files,
            components={component.path: component.key for component in loaded.components},
            used=loaded.used_files,
            used_variables=loaded.used_variable_files,
            includers=loaded.includers,
            common_path=Path(self.config_manager.cfg_root, COMMON_FOLDER_NAME),
        )
        self.source_editor.set_hints(loaded.unused_variables)
        self.source_sync.set_variable_usages(loaded.variable_usages)
        self.page_layout_editor_widget.device_controls.set_device(self.device)
        self.connection.set_device(self.device)
        self.log_stream.set_device(self.device)
        self.page_layout_editor_widget.set_data(
            session=session, device_pages_data=pages_data, page=self._page_after_reload.pop(key, None)
        )
        self._update_draft_actions()
        self.center_stack.setCurrentWidget(self.page_layout_editor_widget)
        if not keep_view:
            self.page_layout_editor_widget.page_preview_widget.fit_to_view()


def create_application_settings():
    """QSettings() without arguments uses these names."""
    QtCore.QCoreApplication.setOrganizationName("openhasp-config-manager")
    QtCore.QCoreApplication.setApplicationName("openhasp-config-manager")
