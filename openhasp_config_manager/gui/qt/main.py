import asyncio
import logging
import os
import shlex
from importlib import metadata
from pathlib import Path
from typing import Any, Optional, List, Dict, Callable, Set, Tuple

import qtawesome as qta

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QActionGroup, QKeySequence, QColor, QPalette
from PyQt6.QtWidgets import (
    QWidget,
    QMainWindow,
    QStackedWidget,
    QDockWidget,
    QProgressBar,
    QLabel,
    QSplitter,
    QToolButton,
    QApplication,
    QMessageBox,
    QVBoxLayout,
)
from openhasp_config_manager.const import DEVICES_FOLDER_NAME, COMMON_FOLDER_NAME
from openhasp_config_manager.gui.domain.device_config_text import set_debug_ansi
from openhasp_config_manager.manager import CONFIG_FILE_NAME
from openhasp_config_manager.deployment import deploy_device
from openhasp_config_manager.gui.domain.draft_files import (
    LoadedDevice,
    load_device,
    plan_save,
    write_save,
    SaveConflictError,
)
from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.config_changes import OwnWrites
from openhasp_config_manager.gui.domain.connection import ConnectionStatus, Severity, LinkState
from openhasp_config_manager.gui.domain.gui_state import (
    SCHEMA_VERSION,
    GuiStateFile,
    describe_connection,
    EditorTab,
    describe_draft,
    describe_editor,
    describe_files,
    describe_object,
    describe_problems,
    now,
    relative,
)
from openhasp_config_manager.gui.domain.page_objects import get_navigable_page_indices
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.config_watcher import ConfigWatcher
from openhasp_config_manager.gui.qt.gui_state_publisher import GuiStatePublisher
from openhasp_config_manager.gui.qt.source_sync import SourceEditorSync
from openhasp_config_manager.gui.qt.connection import ConnectionController
from openhasp_config_manager.gui.qt.log_stream import LogStreamController
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, error_text, run_busy
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.theme import ThemeMode, apply_theme, current_mode, current_colors
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.widgets.code_view import CodeView
from openhasp_config_manager.gui.qt.widgets.file_rendered_view import FileRenderedView
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.file_tree import FileTreeWidget
from openhasp_config_manager.gui.qt.widgets.log_view import LogView
from openhasp_config_manager.gui.qt.widgets.message_panel import MessagePanel, DiskConflictBanner, file_list_text
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.gui.qt.widgets.source_editor import SourceEditorWidget
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.variables import VariableManager

LOGGER = logging.getLogger(__name__)

# the version of the saved arrangement of the docks: a state of another version is not restored
DOCK_STATE_VERSION = 3


class StatusBarController:
    """
    Shows the selected device, the connection to it, the page, the draft state and the last operation in the status bar.
    """

    def __init__(self, window: QMainWindow, status: OperationStatus, on_resync: Callable[[int], None]):
        bar = window.statusBar()
        self._on_resync = on_resync
        self._connection_status = ConnectionStatus()
        self._connection = QToolButton()
        self._connection.setAutoRaise(True)
        self._connection.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._connection.clicked.connect(self._on_connection_clicked)
        self._device = QLabel("No device")
        self._page = QLabel("")
        self._dirty = QLabel("")
        self._operation = QLabel("Ready")
        self._operation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(160)
        self._progress.setMaximumHeight(UiDimensions.two)
        self._progress.hide()

        bar.addWidget(self._operation, 1)
        bar.addPermanentWidget(self._progress)
        bar.addPermanentWidget(self._dirty)
        bar.addPermanentWidget(self._page)
        bar.addPermanentWidget(self._device)
        bar.addPermanentWidget(self._connection)

        status.started.connect(self._on_started)
        status.progressed.connect(self._on_progressed)
        status.succeeded.connect(self._on_succeeded)
        status.failed.connect(self._on_failed)
        self._running = 0

    def set_device(self, name: Optional[str]):
        self._device.setText(name or "No device")

    def set_connection(self, connection_status: ConnectionStatus):
        self._connection_status = connection_status
        text, severity = connection_status.summary
        colors = current_colors()
        color = {
            Severity.NEUTRAL: QApplication.palette().color(QPalette.ColorRole.PlaceholderText),
            Severity.OK: QColor(colors.success),
            Severity.WARNING: QColor(colors.warning),
            Severity.ERROR: QColor(colors.error),
        }[severity]
        self._connection.setVisible(connection_status.link != LinkState.NO_DEVICE)
        self._connection.setText(text)
        self._connection.setIcon(qta.icon("mdi6.circle", color=color))
        self._connection.setToolTip(connection_status.details)
        self._connection.setProperty("severity", severity.value)
        self._connection.style().unpolish(self._connection)
        self._connection.style().polish(self._connection)

    def refresh_theme(self):
        self.set_connection(self._connection_status)

    def _on_connection_clicked(self):
        if self._connection_status.out_of_sync_pages:
            self._on_resync(min(self._connection_status.out_of_sync_pages))

    def set_page(self, index: Optional[int], count: int = 0):
        self._page.setText("" if index is None else f"Page {index}  ·  {count} pages")

    def set_dirty(self, dirty: bool):
        self._dirty.setText("● Modified" if dirty else "")
        self._dirty.setToolTip("The draft differs from the files on disk. Changes are kept until the app is closed.")

    def _set_operation(self, text: str, role: Optional[str] = None):
        self._operation.setText(text)
        self._operation.setProperty("role", role)
        self._operation.style().unpolish(self._operation)
        self._operation.style().polish(self._operation)

    def _on_started(self, description: str):
        self._running += 1
        self._set_operation(f"{description}…")
        self._progress.setRange(0, 0)  # indeterminate until progress is reported
        self._progress.show()

    def _on_progressed(self, done: int, total: int):
        self._progress.setRange(0, total)
        self._progress.setValue(done)

    def _on_succeeded(self, message: str):
        self._finish()
        self._set_operation(message, "success")

    def _on_failed(self, description: str, error: str):
        self._finish()
        self._set_operation(f"{description} failed: {error}", "error")

    def _finish(self):
        self._running = max(0, self._running - 1)
        if self._running == 0:
            self._progress.hide()


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self._cfg_root = Path(config_manager.cfg_root).resolve()
        self.devices: List[Device] = []
        # one draft per (device name, cmd component): the Device objects are created anew on every reload
        self.sessions: Dict[Tuple[str, str], PlateSession] = {}
        self.device: Optional[Device] = None
        self._selected_name: Optional[str] = None
        # the (device name, cmd component) of the draft in the editor
        self._session_key: Optional[Tuple[str, str]] = None
        # the page to show after a draft was reloaded (saved or reverted), per session key
        self._page_after_reload: Dict[Tuple[str, str], int] = {}
        self._discard_drafts_on_close = False
        # what the app wrote itself (Save), to tell its own file changes from those of others
        self._own_writes = OwnWrites()
        # a reload after files changed on disk is running, and more changed meanwhile
        self._reloading_changes: Optional[Set[Path]] = None
        self._changes_during_reload: Set[Path] = set()
        # for the state file (see `_collect_gui_state`)
        self._load_error: Optional[Dict[str, Any]] = None
        self._last_operation: Optional[Dict[str, Any]] = None
        self._disk_changes: List[str] = []
        # select the device of the last session once the devices are loaded the first time
        self._restore_selection = True
        # what is restored on the next start: the selected device, the file for new objects, ...
        self.ui_session = UiSessionStore(Path(config_manager.cfg_root), QSettings())

        self.status = OperationStatus(self)
        self.status.succeeded.connect(lambda message: self._on_operation(True, message))
        self.status.failed.connect(lambda description, error: self._on_operation(False, f"{description}: {error}"))
        # tells tools that edit the config files next to the GUI what the user has open
        self._state_publisher = GuiStatePublisher(GuiStateFile(self._cfg_root), self._collect_gui_state, parent=self)

        self.setWindowTitle("openhasp-config-manager")
        self.setMinimumSize(960, 600)
        self.setDockNestingEnabled(True)

        self.create_basic_layout()
        self._create_menus()
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
        self.disk_changes_banner.reloadRequested.connect(self._reload_draft)
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
        self.source_editor = SourceEditorWidget(self._cfg_root)
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
            self._cfg_root,
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
        self._log_colors_busy = BusyState(self)
        self.log_stream.deviceChanged.connect(self.log_view.clear)
        self.log_stream.entriesReceived.connect(self.log_view.add_entries)
        self.log_stream.stateChanged.connect(lambda state, error: self.log_view.set_link(state, error))
        self.log_stream.colorsMissingChanged.connect(self.log_view.set_colors_missing)
        self.log_view.enableColorsRequested.connect(self._ask_to_enable_log_colors)
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

    def _create_menus(self):
        editor = self.page_layout_editor_widget
        create = UiComponents.create_action

        self.action_save = create(
            self,
            "Save",
            "content-save",
            self.save_draft,
            shortcut=QKeySequence.StandardKey.Save,
            tooltip="Write the changes of the draft into the .jsonl files",
        )
        self.action_revert = create(
            self, "Revert", "restore", self.revert_draft, tooltip="Discard the changes of the draft and load the files again"
        )
        self.action_deploy = create(
            self,
            "Deploy",
            "upload",
            self.deploy_saved_files,
            tooltip="Upload the saved files to the plate, like the deploy command of the CLI. "
            "The plate rebuilds its pages, or restarts if its settings or fonts changed.\nUnsaved changes of the draft are not deployed.",
        )
        # next to the files they act on
        self.file_tree_widget.set_actions(
            [(self.action_save, "content-save"), (self.action_revert, "restore"), (self.action_deploy, "upload")]
        )

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_revert)
        file_menu.addSeparator()
        file_menu.addAction(create(self, "Reload devices", "refresh", self.load_plates, shortcut="Ctrl+R"))
        file_menu.addSeparator()
        file_menu.addAction(create(self, "Quit", "exit-to-app", self.close, shortcut=QKeySequence.StandardKey.Quit))

        edit_menu = self.menuBar().addMenu("&Edit")
        for action in [
            editor.action_undo,
            editor.action_redo,
            None,
            editor.action_edit_mode,
            editor.action_snap,
            None,
            editor.action_copy,
            editor.action_paste,
            editor.action_duplicate,
            editor.action_delete,
        ]:
            if action is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(action)

        page_menu = self.menuBar().addMenu("&Page")
        for action in [
            editor.action_previous_page,
            editor.action_next_page,
            None,
            editor.plate.action_clear,
        ]:
            if action is None:
                page_menu.addSeparator()
            else:
                page_menu.addAction(action)

        plate_menu = self.menuBar().addMenu("P&late")
        for action in [editor.plate.action_live_preview, editor.plate.action_restore_plate, None, self.action_deploy]:
            if action is None:
                plate_menu.addSeparator()
            else:
                plate_menu.addAction(action)

        view_menu = self.menuBar().addMenu("&View")
        for action in [editor.action_zoom_in, editor.action_zoom_out, editor.action_zoom_fit]:
            view_menu.addAction(action)
        view_menu.addSeparator()
        for dock in [self.devices_dock, self.properties_dock, self.jsonl_dock, self.page_jsonl_dock, self.logs_dock]:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(
            create(
                self,
                "Restore default layout",
                "view-dashboard-outline",
                self.restore_default_layout,
                tooltip="Show all panels again and put them back where they were at the first start",
            )
        )
        view_menu.addSeparator()

        theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        for mode, title, icon in [(ThemeMode.DARK, "Dark", "weather-night"), (ThemeMode.LIGHT, "Light", "weather-sunny")]:
            action = create(self, title, icon, lambda mode=mode: self.set_theme(mode), checkable=True)
            action.setChecked(current_mode() == mode)
            theme_group.addAction(action)
            theme_menu.addAction(action)

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

    # --- log colors ---

    def _ask_to_enable_log_colors(self):
        device = self.device
        if device is None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Enable colors in the log?")
        box.setText(f"Ask {device.name} to send colors in its log?")
        box.setInformativeText(
            "openHASP tells the level of a log line (error, warning, ...) only with the color of the line. Without colors the "
            "level is guessed from the words of the line.\n\n"
            'This turns on "debug.ansi" of the plate, which also puts the colors into its serial output. It takes effect at once. '
            "A deploy sends the config.json again, so the setting is lost there unless config.json has it too."
        )
        both = box.addButton("Enable and update config.json", QMessageBox.ButtonRole.AcceptRole)
        plate_only = box.addButton("Enable on the plate only", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(both)
        box.exec()
        if box.clickedButton() in (both, plate_only):
            self.enable_log_colors(update_config=box.clickedButton() is both)

    def enable_log_colors(self, update_config: bool):
        """
        Turns on the colors of the log at the selected plate.
        :param update_config: also set it in the `config.json` of the device, so the next deploy keeps it
        """
        device = self.device
        name = device.name
        if update_config:
            try:
                self._set_ansi_in_config_file(Path(device.path, CONFIG_FILE_NAME))
            except (OSError, ValueError) as ex:
                self.status.failed.emit(f"Updating config.json of {name}", error_text(ex))
                return
        run_busy(
            self.log_stream.set_colors(True),
            self._log_colors_busy,
            self.status,
            f"Enabling colors in the log of {name}",
            success_message=f"{name} sends colors in its log now",
        )

    def _set_ansi_in_config_file(self, path: Path):
        text = path.read_text()
        changed = set_debug_ansi(text, True)
        if changed != text:
            path.write_text(changed)
            self._own_writes.written(path, changed)

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
        self._watcher = ConfigWatcher(self._cfg_root, ignored_roots=[output_root], parent=self)
        self._watcher.changed.connect(self._on_config_changed)
        self._watcher.start()

    def _on_config_changed(self, paths: Set[Path]):
        """
        Files changed in the config directory. A draft without changes follows them. A draft with changes is never
        replaced: the user chooses in a banner (Save detects the same conflict too, but only when it is too late).
        """
        paths = self._own_writes.foreign(paths)
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
        self._own_writes.written(path.resolve(), text)
        self.status.succeeded.emit(f"Saved {path.name}")
        if self.device is not None:
            self._apply_changes_to_draft({path.resolve()})

    def _show_disk_changes(self, paths: Set[Path]):
        """Offer to reload, if the changes can affect the device of the draft."""
        devices_dir = self._cfg_root / DEVICES_FOLDER_NAME
        affecting = sorted(
            path for path in paths if path.is_relative_to(self.device.path.resolve()) or not path.is_relative_to(devices_dir)
        )
        if affecting:
            self._disk_changes = [str(path.relative_to(self._cfg_root)) for path in affecting]
            self.disk_changes_banner.show_message(
                f"Changed on disk since this draft was loaded: {file_list_text(self._disk_changes)}"
            )

    def _reload_changed_files(self, paths: Set[Path]):
        """Load the device again, in the background and without leaving the editor: the page and zoom stay."""
        name = self._selected_name
        self._reloading_changes = paths
        self._changes_during_reload = set()
        self._page_after_reload[self._session_key] = self.page_layout_editor_widget.current_index
        key = self._session_key

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
            names = sorted(str(path.relative_to(self._cfg_root)) for path in changes)
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
        self._last_operation = {"ok": ok, "message": message, "time": now()}
        self._state_publisher.request()

    def _set_load_error(self, device: Optional[str], ex: Exception):
        self._load_error = {"device": device, "message": error_text(ex), "time": now()}
        self._state_publisher.request()

    def _collect_gui_state(self, running: bool = True) -> Dict[str, Any]:
        """The state for the state file (see `GuiStateFile`), as the GUI is now."""
        editor = self.page_layout_editor_widget
        root = self._cfg_root
        session = self.session
        device = None
        problems: List[Dict[str, Any]] = []
        if session is not None and editor.session is session and session.is_loaded:
            screen = self.device.config.openhasp_config_manager.device.screen
            device = {
                "name": self.device.name,
                "folder": relative(self.device.path, root),
                "cmd": self._session_key[1],
                "screen": {"width": screen.width, "height": screen.height},
                "files": describe_files(session.components, session.working_objects, root),
                "page": editor.current_index,
                "pages": get_navigable_page_indices(session.working_objects),
                "edit_mode": editor.action_edit_mode.isChecked(),
                "live_preview": editor.plate.live,
                "selection": [
                    describe_object(session, item.obj_data, root) for item in editor.page_preview_widget.selected_items()
                ],
                "new_objects_file": None
                if editor.target_component is None
                else relative(next(c.path for c in session.components if c.key == editor.target_component), root),
                "draft": describe_draft(session, root),
            }
            problems = describe_problems(session, editor.problems, root, self.devices)
        return {
            "schema": SCHEMA_VERSION,
            "app": "openhasp-config-manager",
            "version": metadata.version("openhasp-config-manager"),
            "running": running,
            "pid": os.getpid(),
            "updated": now(),
            "config_dir": str(root),
            "check_command": f"openhasp-config-manager check -c {shlex.quote(str(root))} --json",
            "devices": [device.name for device in self.devices],
            "device": device,
            "editor": describe_editor(self.code_view.mode.value, self._editor_tabs(), self.source_editor.current_file, root),
            "problems": problems,
            "load_error": self._load_error,
            "files_changed_on_disk": [] if self.disk_changes_banner.isHidden() else self._disk_changes,
            "connection": describe_connection(self.connection.status),
            "last_operation": self._last_operation,
        }

    def _editor_tabs(self) -> List[EditorTab]:
        tabs = []
        for path in self.source_editor.open_files:
            buffer = self.source_editor.buffer_of(path)
            line, column = self.source_editor.editor_of(path).cursor_line_column
            tabs.append(EditorTab(path, buffer.is_dirty, buffer.conflict, line, column))
        return tabs

    # --- draft ---

    @property
    def session(self) -> Optional[PlateSession]:
        return None if self.device is None else self.sessions.get(self._session_key)

    def _update_draft_actions(self):
        dirty = self.session is not None and self.session.is_dirty
        self.action_save.setEnabled(dirty)
        self.action_revert.setEnabled(dirty)
        self.action_deploy.setEnabled(self.device is not None and not self.page_layout_editor_widget.busy.busy)

    def save_draft(self) -> bool:
        """
        Write the changes of the draft into the source files.
        :return: whether the draft was saved
        """
        session = self.session
        if session is None or not session.is_dirty:
            return False
        try:
            changes = plan_save(session)
        except (SaveConflictError, ValueError) as ex:
            QMessageBox.critical(self, "Save failed", error_text(ex))
            return False

        common = [change for change in changes if change.is_common]
        if common:
            paths = [change.path for change in common]
            others = sorted(
                device.name
                for device in self.devices
                if device.name != self.device.name and any(component.path in paths for component in device.jsonl)
            )
            answer = QMessageBox.question(
                self,
                "Save shared files",
                "These files are in the common folder and shared with other devices:\n\n"
                + "\n".join(str(path) for path in paths)
                + (f"\n\nThe change also affects: {', '.join(others)}." if others else "")
                + "\n\nSave them anyway?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Save:
                return False

        try:
            write_save(changes)
        except OSError as ex:
            QMessageBox.critical(self, "Save failed", error_text(ex))
            return False
        for change in changes:
            self._own_writes.written(change.path.resolve(), change.content)
        # own writes are no change on disk for the watcher, but open tabs of the files must follow them
        self.source_editor.external_changes({change.path.resolve() for change in changes})
        # the files are what the draft holds now: no need to load them again
        session.mark_saved({change.path: change.content for change in changes})
        self.status.succeeded.emit(f"Saved {len(changes)} file{'' if len(changes) == 1 else 's'}")
        return True

    def deploy_saved_files(self):
        """Deploy the files of the current device as they are on disk, like the deploy command of the CLI."""
        if self.device is None:
            return
        name = self.device.name
        if self.session is not None and self.session.is_dirty:
            box = QMessageBox(
                QMessageBox.Icon.Question,
                "Deploy",
                f"The draft of {name} has unsaved changes. Deploy uploads only the saved files.",
                parent=self,
            )
            save = box.addButton("Save and deploy", QMessageBox.ButtonRole.AcceptRole)
            saved_only = box.addButton("Deploy without the changes", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(save)
            box.exec()
            if box.clickedButton() is save:
                if not self.save_draft():
                    return
            elif box.clickedButton() is not saved_only:
                return

        # the plate shows its files after the deploy, not the draft
        self.page_layout_editor_widget.plate.stop_live_preview()
        # its own ConfigManager: the editor may analyze the config directory at the same time (after Save)
        config_manager = ConfigManager(
            cfg_root=self.config_manager.cfg_root,
            output_root=self.config_manager.output_root,
            variable_manager=VariableManager(cfg_root=self.config_manager.cfg_root),
        )

        async def __deploy() -> bool:
            devices = await asyncio.to_thread(config_manager.analyze)
            device = next((device for device in devices if device.name == name), None)
            if device is None:
                raise ValueError(f"{name} is not in the config directory anymore")
            return await deploy_device(config_manager, device)

        def __on_success(changed: bool):
            if changed:
                self.status.succeeded.emit(f"Deployed {name}: the plate loaded the new files")
                self.connection.plate_restored()
            else:
                self.status.succeeded.emit(f"{name} is already up to date")

        run_busy(
            __deploy(),
            busy=self.page_layout_editor_widget.busy,
            status=self.status,
            description=f"Deploying the saved files of {name}",
            on_success=__on_success,
        )

    def revert_draft(self):
        session = self.session
        if session is None or not session.is_dirty:
            return
        answer = QMessageBox.question(
            self,
            "Revert",
            f"Discard all changes of the draft of {self.device.name} and load its files again?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Discard:
            self._reload_draft()

    def _reload_draft(self):
        """Drop the draft of the current device and load it from disk, on the same page."""
        self.disk_changes_banner.hide()
        self.sessions.pop(self._session_key)
        self._page_after_reload[self._session_key] = self.page_layout_editor_widget.current_index
        self.on_device_selected(self.device.name)

    def select_device(self, loaded: LoadedDevice, keep_view: bool = False):
        """
        :param keep_view: the same device is loaded again: don't change the zoom
        """
        self.device = loaded.device
        self._load_error = None
        pages_data = OpenHaspDevicePagesData(
            device=loaded.device, name=loaded.cmd_component.name, jsonl_components=loaded.jsonl_components
        )
        key = (loaded.device.name, pages_data.name)
        session = self.sessions.setdefault(key, PlateSession(device=loaded.device))
        session.device = loaded.device
        # a draft without changes follows the files on disk, one with changes is kept (Save detects conflicts)
        if not session.is_loaded or not session.is_dirty:
            session.load(loaded.components, loaded.renderer)
        self._session_key = key
        self.file_tree_widget.set_files(
            loaded.files,
            components={component.path: component.key for component in loaded.components},
            used=loaded.used_files,
            used_variables=loaded.used_variable_files,
            common_path=Path(self.config_manager.cfg_root, COMMON_FOLDER_NAME),
        )
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
