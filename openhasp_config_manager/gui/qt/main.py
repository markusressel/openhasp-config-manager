import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Callable

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
)
from orjson import orjson

from openhasp_config_manager.const import DEVICES_FOLDER_NAME
from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.connection import ConnectionStatus, Severity, LinkState
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.connection import ConnectionController
from openhasp_config_manager.gui.qt.operations import OperationStatus, error_text
from openhasp_config_manager.gui.qt.theme import ThemeMode, apply_theme, current_mode, current_colors
from openhasp_config_manager.gui.qt.util import run_async
from openhasp_config_manager.gui.qt.widgets.device_controls import DeviceControlsWidget
from openhasp_config_manager.gui.qt.widgets.device_list import DeviceListWidget
from openhasp_config_manager.gui.qt.widgets.message_panel import MessagePanel
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import CmdComponent
from openhasp_config_manager.openhasp_client.model.device import Device

LOGGER = logging.getLogger(__name__)

# the cmd component whose pages the editor shows
BOOT_CMD = "boot.cmd"


@dataclass
class LoadedDevice:
    devices: List[Device]
    device: Device
    pages_data: OpenHaspDevicePagesData
    # the normalized objects of the jsonl components
    raw_data: OrderedDict[str, List[Dict]]


def load_device(config_manager: ConfigManager, name: str) -> LoadedDevice:
    """
    Analyze the config directory again (to reflect changes on disk) and load the pages of a device.
    Runs in a worker thread: it renders templates and must not block the UI.
    """
    devices = config_manager.analyze()
    device = next((d for d in devices if d.name == name), None)
    if device is None:
        raise RuntimeError(f"The device '{name}' no longer exists in {Path(config_manager.cfg_root, DEVICES_FOLDER_NAME)}.")

    relevant_components = config_manager.find_relevant_components(device)
    boot_cmd_component: Optional[CmdComponent] = next((c for c in relevant_components if c.name == BOOT_CMD), None)
    if boot_cmd_component is None:
        raise RuntimeError(f"{device.path} has no {BOOT_CMD}. The editor shows the pages that {BOOT_CMD} loads.")

    jsonl_components = config_manager.determine_device_jsonl_component_order_for_cmd(
        device=device,
        cmd_component=boot_cmd_component,
    )

    device_processor = config_manager.create_device_processor(device)
    raw_data = OrderedDict()
    for jsonl_component in jsonl_components:
        normalized_jsonl_component = device_processor.normalize(device, jsonl_component)
        raw_data[jsonl_component.name] = list(map(orjson.loads, normalized_jsonl_component.splitlines()))

    return LoadedDevice(
        devices=devices,
        device=device,
        pages_data=OpenHaspDevicePagesData(device=device, name=boot_cmd_component.name, jsonl_components=jsonl_components),
        raw_data=raw_data,
    )


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
        self.sessions: Dict[Device, PlateSession] = {}
        self.device: Optional[Device] = None
        self._selected_name: Optional[str] = None

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

        file_menu = self.menuBar().addMenu("&File")
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
        # Update or create sessions for each device
        for device in self.devices:
            if device not in self.sessions:
                self.sessions[device] = PlateSession(device=device)
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

    def select_device(self, loaded: LoadedDevice):
        self.device = loaded.device
        session = self.sessions[loaded.device]
        self.device_control_widget.set_device(self.device)
        self.connection.set_device(self.device)
        self.page_layout_editor_widget.set_data(session=session, device_pages_data=loaded.pages_data, raw_data=loaded.raw_data)
        self.center_stack.setCurrentWidget(self.page_layout_editor_widget)
        self.page_layout_editor_widget.page_preview_widget.fit_to_view()


def create_application_settings():
    """QSettings() without arguments uses these names."""
    QtCore.QCoreApplication.setOrganizationName("openhasp-config-manager")
    QtCore.QCoreApplication.setApplicationName("openhasp-config-manager")
