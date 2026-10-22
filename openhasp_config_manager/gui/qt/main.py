import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Callable, Tuple

import qtawesome as qta

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QActionGroup, QKeySequence, QColor, QPalette
from PyQt6.QtWidgets import (
    QWidget,
    QMainWindow,
    QStackedWidget,
    QDockWidget,
    QScrollArea,
    QFrame,
    QProgressBar,
    QLabel,
    QSplitter,
    QToolButton,
    QApplication,
    QMessageBox,
)
from openhasp_config_manager.const import DEVICES_FOLDER_NAME
from openhasp_config_manager.gui.domain.draft_files import (
    LoadedDevice,
    load_device,
    plan_save,
    write_save,
    SaveConflictError,
)
from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.connection import ConnectionStatus, Severity, LinkState
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.connection import ConnectionController
from openhasp_config_manager.gui.qt.operations import OperationStatus, error_text
from openhasp_config_manager.gui.qt.theme import ThemeMode, apply_theme, current_mode, current_colors
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.widgets.device_controls import DeviceControlsWidget
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.message_panel import MessagePanel
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device

LOGGER = logging.getLogger(__name__)


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
        self.devices: List[Device] = []
        # one draft per (device name, cmd component): the Device objects are created anew on every reload
        self.sessions: Dict[Tuple[str, str], PlateSession] = {}
        self.device: Optional[Device] = None
        self._selected_name: Optional[str] = None
        # the (device name, cmd component) of the draft in the editor
        self._session_key: Optional[Tuple[str, str]] = None
        # the page to show after a draft was reloaded (saved or reverted), per session key
        self._page_after_reload: Dict[Tuple[str, str], int] = {}

        self.status = OperationStatus(self)

        self.setWindowTitle("openhasp-config-manager")
        self.setMinimumSize(960, 600)
        self.setDockNestingEnabled(True)

        self.create_basic_layout()
        self._create_menus()
        self._restore_window_state()
        self.load_plates()

    # --- layout ---

    def create_basic_layout(self):
        self.page_layout_editor_widget = PageLayoutEditorWidget(status=self.status)
        self.page_layout_editor_widget.pageChanged.connect(lambda index, count: self.status_bar.set_page(index, count))
        self.page_layout_editor_widget.dirtyChanged.connect(lambda dirty: self.status_bar.set_dirty(dirty))
        self.page_layout_editor_widget.dirtyChanged.connect(lambda _: self._update_draft_actions())
        self.addToolBar(self.page_layout_editor_widget.toolbar)

        # center: a placeholder (no device, loading, errors) or the editor
        self.message_panel = MessagePanel()
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.message_panel)
        self.center_stack.addWidget(self.page_layout_editor_widget)
        self.setCentralWidget(self.center_stack)

        # left: devices and the controls of the selected device
        self.device_list_widget = DeviceListWidget()
        self.device_list_widget.deviceSelected.connect(self.on_device_selected)
        self.device_list_widget.reloadClicked.connect(self.load_plates)
        self.device_control_widget = DeviceControlsWidget(status=self.status)

        sidebar = QSplitter(Qt.Orientation.Vertical)
        sidebar.addWidget(self.device_list_widget)
        sidebar.addWidget(self._scrollable(self.device_control_widget))
        sidebar.setStretchFactor(0, 1)
        sidebar.setChildrenCollapsible(False)
        sidebar.setMinimumWidth(260)
        self.devices_dock = self._add_dock("Devices", "devices_dock", sidebar, Qt.DockWidgetArea.LeftDockWidgetArea)

        # right: the properties of the selected object
        self.properties_dock = self._add_dock(
            "Properties",
            "properties_dock",
            self.page_layout_editor_widget.property_editor,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )

        # bottom: the JSONL of the page, collapsible
        self.jsonl_dock = self._add_dock(
            "JSONL", "jsonl_dock", self.page_layout_editor_widget.jsonl_preview, Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.resizeDocks([self.jsonl_dock], [200], Qt.Orientation.Vertical)
        self.resizeDocks([self.devices_dock, self.properties_dock], [280, 360], Qt.Orientation.Horizontal)

        self.status_bar = StatusBarController(self, self.status, on_resync=self.page_layout_editor_widget.resync_page)

        # the connection to the selected plate
        self.connection = ConnectionController(self)
        self.connection.changed.connect(self.status_bar.set_connection)
        self.status_bar.set_connection(self.connection.status)
        self.page_layout_editor_widget.pageOutOfSync.connect(self.connection.page_out_of_sync)
        self.page_layout_editor_widget.pageDeployed.connect(self.connection.page_deployed)
        for busy in [self.page_layout_editor_widget.busy, self.device_control_widget.busy]:
            busy.changed.connect(lambda _: self._update_sending())

    def _scrollable(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _add_dock(self, title: str, name: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(area, dock)
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
        toolbar = editor.toolbar
        first = toolbar.actions()[0]
        toolbar.insertAction(first, self.action_save)
        toolbar.insertAction(first, self.action_revert)
        toolbar.insertSeparator(first)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_revert)
        file_menu.addSeparator()
        file_menu.addAction(create(self, "Reload devices", "refresh", self.load_plates, shortcut="Ctrl+R"))
        file_menu.addSeparator()
        file_menu.addAction(create(self, "Quit", "exit-to-app", self.close, shortcut=QKeySequence.StandardKey.Quit))

        edit_menu = self.menuBar().addMenu("&Edit")
        for action in [editor.action_edit_mode, editor.action_snap, None, editor.action_duplicate, editor.action_delete]:
            if action is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(action)

        page_menu = self.menuBar().addMenu("&Page")
        for action in [
            editor.action_previous_page,
            editor.action_next_page,
            None,
            editor.action_sync,
            editor.action_clear,
            editor.action_deploy,
        ]:
            if action is None:
                page_menu.addSeparator()
            else:
                page_menu.addAction(action)

        view_menu = self.menuBar().addMenu("&View")
        for action in [editor.action_zoom_in, editor.action_zoom_out, editor.action_zoom_fit]:
            view_menu.addAction(action)
        view_menu.addSeparator()
        for dock in [self.devices_dock, self.properties_dock, self.jsonl_dock]:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()

        theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        for mode, title, icon in [(ThemeMode.DARK, "Dark", "weather-night"), (ThemeMode.LIGHT, "Light", "weather-sunny")]:
            action = create(self, title, icon, lambda mode=mode: self.set_theme(mode), checkable=True)
            action.setChecked(current_mode() == mode)
            theme_group.addAction(action)
            theme_menu.addAction(action)

    def _update_sending(self):
        self.connection.set_sending(self.page_layout_editor_widget.busy.busy or self.device_control_widget.busy.busy)

    def set_theme(self, mode: ThemeMode):
        apply_theme(mode)
        ThemedIcons.refresh()
        self.status_bar.refresh_theme()
        self.page_layout_editor_widget.jsonl_preview.refresh_theme()
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
            self.restoreState(state)

    def closeEvent(self, event):
        dirty = [f"{device} ({cmd})" for (device, cmd), session in self.sessions.items() if session.is_dirty]
        if dirty:
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
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())
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
        elif self.device is None:
            self._show_no_device_selected()

    def _on_devices_failed(self, ex: Exception):
        self.device_list_widget.show_error()
        self.message_panel.show_error(
            title="Could not load the config directory",
            error=f"{self.config_manager.cfg_root}\n\n{error_text(ex)}",
            retry=self.load_plates,
        )
        self.center_stack.setCurrentWidget(self.message_panel)

    def _set_devices(self, devices: List[Device]):
        self.devices = devices
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
        if self.device is None or self.device.name != name:
            # another device: start without a connection and in interaction mode, not editing its objects by accident
            self.connection.set_device(None)
            self.page_layout_editor_widget.set_edit_mode(False)
        self.device = None
        self.device_control_widget.set_device(None)
        self.page_layout_editor_widget.clear()
        self.status_bar.set_device(name)
        self.status_bar.set_page(None)
        self.status_bar.set_dirty(False)
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
            self.message_panel.show_error(
                title=f"Could not load {name}",
                error=error_text(ex),
                retry=lambda: self.on_device_selected(name),
            )

        run_async(__load(), on_success=__on_success, on_error=__on_error)

    # --- draft ---

    @property
    def session(self) -> Optional[PlateSession]:
        return None if self.device is None else self.sessions.get(self._session_key)

    def _update_draft_actions(self):
        dirty = self.session is not None and self.session.is_dirty
        self.action_save.setEnabled(dirty)
        self.action_revert.setEnabled(dirty)

    def save_draft(self):
        """Write the changes of the draft into the source files, then load them again."""
        session = self.session
        if session is None or not session.is_dirty:
            return
        try:
            changes = plan_save(session)
        except (SaveConflictError, ValueError) as ex:
            QMessageBox.critical(self, "Save failed", error_text(ex))
            return

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
                return

        try:
            write_save(changes)
        except OSError as ex:
            QMessageBox.critical(self, "Save failed", error_text(ex))
            return
        self.status.succeeded.emit(f"Saved {len(changes)} file{'' if len(changes) == 1 else 's'}")
        self._reload_draft()

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
        self.sessions.pop(self._session_key)
        self._page_after_reload[self._session_key] = self.page_layout_editor_widget.current_index
        self.on_device_selected(self.device.name)

    def select_device(self, loaded: LoadedDevice):
        self.device = loaded.device
        pages_data = OpenHaspDevicePagesData(
            device=loaded.device, name=loaded.cmd_component.name, jsonl_components=loaded.jsonl_components
        )
        key = (loaded.device.name, pages_data.name)
        session = self.sessions.setdefault(key, PlateSession(device=loaded.device))
        session.device = loaded.device
        if not session.is_loaded:
            session.load(loaded.components, loaded.renderer)
        self._session_key = key
        self.device_control_widget.set_device(self.device)
        self.connection.set_device(self.device)
        self.page_layout_editor_widget.set_data(
            session=session, device_pages_data=pages_data, page=self._page_after_reload.pop(key, None)
        )
        self._update_draft_actions()
        self.center_stack.setCurrentWidget(self.page_layout_editor_widget)
        self.page_layout_editor_widget.page_preview_widget.fit_to_view()


def create_application_settings():
    """QSettings() without arguments uses these names."""
    QtCore.QCoreApplication.setOrganizationName("openhasp-config-manager")
    QtCore.QCoreApplication.setApplicationName("openhasp-config-manager")
