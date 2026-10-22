import asyncio
import logging
from collections import OrderedDict
from typing import List, Dict, Optional, Any, Callable

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget, QToolBar, QComboBox, QMessageBox, QToolButton

from openhasp_config_manager.gui.domain.page_objects import (
    OpenHASPWidgetType,
    get_page_objects,
    get_navigable_page_indices,
    count_objects,
    next_free_id,
    is_id_used,
    create_object,
    find_target_component,
    add_object,
    remove_object,
    duplicate_object,
)
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, run_busy, error_text
from openhasp_config_manager.gui.qt.async_bridge import qBridge
from openhasp_config_manager.gui.qt.widgets.message_panel import ErrorBanner
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_picker import OpenHASPWidgetPicker
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_property_editor import OpenHASPWidgetPropertyEditor
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

LOGGER = logging.getLogger(__name__)

# delay between two objects when deploying a page, to avoid overwhelming the device
DEPLOY_DELAY_SECONDS = 0.1

NUDGE_STEP = 1
NUDGE_STEP_LARGE = 10


class PageLayoutEditorWidget(QWidget):
    """
    The page layout editor: the plate preview with the widget picker, and the editor actions in `toolbar`.
    The property editor (`property_editor`) and the JSONL view (`jsonl_preview`) belong to it,
    but are placed by the main window.
    """

    # (current page index, number of navigable pages)
    pageChanged = QtCore.pyqtSignal(int, int)
    dirtyChanged = QtCore.pyqtSignal(bool)
    # a page on the device may differ from the draft: sending it failed, or it was cleared
    pageOutOfSync = QtCore.pyqtSignal(int)
    pageDeployed = QtCore.pyqtSignal(int)

    def __init__(self, status: OperationStatus):
        super().__init__()
        self.status = status
        self.busy = BusyState(self)
        self.busy.changed.connect(lambda _: self._update_actions())

        self.session: Optional[PlateSession] = None
        self.device_pages_data: Optional[OpenHaspDevicePagesData] = None
        self.current_index = 1
        self.page_objects: List[Dict] = []

        self.property_editor = OpenHASPWidgetPropertyEditor()
        self.property_editor.removeObjectClicked.connect(self.remove_selected_objects)
        self.property_editor.duplicateObjectClicked.connect(self.duplicate_selected_objects)
        self.property_editor.propertyChanged.connect(self._on_property_changed)
        self.property_editor.set_validator(self._validate_property)

        self.jsonl_preview = PageJsonlPreviewWidget()

        self._create_layout()
        self._create_actions()
        self._create_toolbar()

        self.page_preview_widget.set_mode(PreviewMode.Interact)
        self._update_actions()

    @property
    def working_objects(self) -> OrderedDict[str, List[Dict]]:
        return self.session.working_objects

    @property
    def edit_mode(self) -> bool:
        return self.page_preview_widget.mode == PreviewMode.Edit

    # --- layout ---

    def _create_layout(self):
        row = UiComponents.create_row(parent=self)

        self.widget_picker = OpenHASPWidgetPicker()
        self.widget_picker.addItem.connect(self.add_object)
        row.addWidget(self.widget_picker)

        column = UiComponents.create_column()
        row.addLayout(column, 1)

        self.error_banner = ErrorBanner()
        column.addWidget(self.error_banner)

        self.page_preview_widget = PagePreviewWidget()
        self.page_preview_widget.buttonClicked.connect(self.__on_preview_layout_button_clicked)
        self.page_preview_widget.modeChanged.connect(self._on_editor_mode_changed)
        self.page_preview_widget.selectionChanged.connect(self._on_openhasp_widget_selection_changed)
        self.page_preview_widget.itemsMoved.connect(self._on_items_moved)
        self.page_preview_widget.addObjectRequested.connect(lambda: self.add_object(OpenHASPWidgetType.LABEL))
        column.addWidget(self.page_preview_widget, 1)

    def _create_actions(self):
        create = UiComponents.create_action
        canvas = Qt.ShortcutContext.WidgetWithChildrenShortcut

        self.action_previous_page = create(
            self, "Previous page", "chevron-left", self._on_previous_page_clicked, shortcut="Alt+Left"
        )
        self.action_next_page = create(self, "Next page", "chevron-right", self._on_next_page_clicked, shortcut="Alt+Right")

        self.page_combo = QComboBox()
        self.page_combo.setToolTip("Page")
        self.page_combo.setMinimumContentsLength(8)
        self.page_combo.activated.connect(lambda i: self._go_to_page(self.page_combo.itemData(i)))

        self.action_edit_mode = create(
            self,
            "Edit mode",
            "pencil",
            shortcut="Ctrl+E",
            tooltip="Edit mode: select, move and change objects. Off: interact with the page like on the plate",
            checkable=True,
        )
        self.action_edit_mode.toggled.connect(self._on_edit_mode_toggled)

        self.action_snap = create(
            self,
            "Snap",
            "grid",
            shortcut="Ctrl+G",
            tooltip="Snap to the grid and to other objects (hold Alt to move freely)",
            checkable=True,
        )
        self.action_snap.setChecked(True)
        self.action_snap.toggled.connect(self.page_preview_widget.set_snap_enabled)

        self.action_duplicate = create(
            self, "Duplicate", "content-copy", self.duplicate_selected_objects, shortcut="Ctrl+D", context=canvas
        )
        self.action_delete = create(self, "Remove", "delete", self.remove_selected_objects, shortcut="Del", context=canvas)

        self.action_zoom_in = create(
            self, "Zoom in", "magnify-plus-outline", self.page_preview_widget.zoom_in, shortcut="Ctrl++"
        )
        self.action_zoom_out = create(
            self, "Zoom out", "magnify-minus-outline", self.page_preview_widget.zoom_out, shortcut="Ctrl+-"
        )
        self.action_zoom_fit = create(
            self, "Fit to window", "fit-to-screen-outline", self.page_preview_widget.fit_to_view, shortcut="Ctrl+0"
        )

        self.action_sync = create(
            self,
            "Sync",
            "sync",
            tooltip="Show the page of the editor on the real device",
            checkable=True,
        )
        self.action_sync.toggled.connect(self._on_sync_with_real_device_toggled)
        self.action_deploy = create(
            self,
            "Deploy",
            "upload",
            self._on_deploy_page_clicked,
            tooltip="Clear the page on the device and send all of its objects",
        )
        self.action_clear = create(
            self, "Clear", "eraser", self._on_clear_page_clicked, tooltip="Clear the page on the device"
        )

        # keyboard only, while the preview has the focus
        canvas_actions = [
            self.action_delete,
            self.action_duplicate,
            create(self, "Previous page", "chevron-left", self._on_previous_page_clicked, shortcut="PgUp", context=canvas),
            create(self, "Next page", "chevron-right", self._on_next_page_clicked, shortcut="PgDown", context=canvas),
        ]
        for key, dx, dy in [("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)]:
            for modifier, step in [("", NUDGE_STEP), ("Shift+", NUDGE_STEP_LARGE)]:
                canvas_actions.append(
                    create(
                        self,
                        f"Nudge {key.lower()}",
                        "arrow-all",
                        lambda dx=dx, dy=dy, step=step: self.nudge_selected_objects(dx * step, dy * step),
                        shortcut=f"{modifier}{key}",
                        context=canvas,
                    )
                )
        self.page_preview_widget.addActions(canvas_actions)

    def _create_toolbar(self):
        self.toolbar = QToolBar("Editor")
        self.toolbar.setObjectName("editor_toolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)

        icon_only: List[QAction] = []

        self.toolbar.addAction(self.action_previous_page)
        self.toolbar.addWidget(self.page_combo)
        self.toolbar.addAction(self.action_next_page)
        icon_only += [self.action_previous_page, self.action_next_page]
        self.toolbar.addSeparator()

        self.toolbar.addAction(self.action_edit_mode)
        self.toolbar.addAction(self.action_snap)
        self.toolbar.addAction(self.action_duplicate)
        self.toolbar.addAction(self.action_delete)
        icon_only += [self.action_duplicate, self.action_delete]
        self.toolbar.addSeparator()

        self.toolbar.addAction(self.action_zoom_out)
        self.toolbar.addAction(self.action_zoom_fit)
        self.toolbar.addAction(self.action_zoom_in)
        icon_only += [self.action_zoom_out, self.action_zoom_fit, self.action_zoom_in]

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        self.toolbar.addWidget(spacer)

        self.toolbar.addAction(self.action_sync)
        self.toolbar.addAction(self.action_clear)
        self.toolbar.addAction(self.action_deploy)

        for action in icon_only:
            button: QToolButton = self.toolbar.widgetForAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

    def _update_actions(self):
        has_data = self.session is not None
        pages = get_navigable_page_indices(self.working_objects) if has_data else []
        can_navigate = len(pages) > 1 or (len(pages) == 1 and self.current_index not in pages)
        has_selection = bool(self.page_preview_widget.selected_items())
        busy = self.busy.busy

        for action in [
            self.action_edit_mode,
            self.action_snap,
            self.action_zoom_in,
            self.action_zoom_out,
            self.action_zoom_fit,
            self.action_sync,
        ]:
            action.setEnabled(has_data)
        self.page_combo.setEnabled(has_data and self.page_combo.count() > 1)
        self.action_previous_page.setEnabled(can_navigate)
        self.action_next_page.setEnabled(can_navigate)
        self.action_duplicate.setEnabled(self.edit_mode and has_selection)
        self.action_delete.setEnabled(self.edit_mode and has_selection)
        self.action_deploy.setEnabled(has_data and not busy and len(self.page_objects) > 0)
        self.action_clear.setEnabled(has_data and not busy)
        self.widget_picker.setEnabled(has_data and len(self.working_objects) > 0)

    # --- data ---

    def clear(self):
        self.session = None
        self.device_pages_data = None
        self.current_index = 1
        self.page_objects = []
        self.page_preview_widget.set_objects([])
        self.jsonl_preview.set_objects([])
        self.error_banner.hide()
        self._update_actions()

    def set_data(
        self,
        session: PlateSession,
        device_pages_data: OpenHaspDevicePagesData,
        raw_data: OrderedDict[str, List[Dict]],
    ):
        """
        :param raw_data: the normalized objects of the jsonl components, loaded into the session if it has no draft yet
        """
        self.session = session
        self.device_pages_data = device_pages_data
        self.error_banner.hide()

        if not self.session.working_objects:
            self.session.load_from_disk(raw_data)

        screen = device_pages_data.device.config.openhasp_config_manager.device.screen
        self.page_preview_widget.set_screen_size(screen.width, screen.height)

        pages = get_navigable_page_indices(self.working_objects)
        self.set_page_index(pages[0] if pages else 1)
        self.dirtyChanged.emit(self.session.is_dirty)

    def set_page_index(self, index: int):
        LOGGER.debug(f"Setting page index {index}")
        self.current_index = index
        self.page_objects = get_page_objects(self.working_objects, index=index)
        self.page_preview_widget.set_objects(self.page_objects)
        self.jsonl_preview.set_objects(self.page_objects)
        self.property_editor.set_editable_widgets([])

        pages = get_navigable_page_indices(self.working_objects)
        self._update_page_combo(pages)
        self._update_empty_hint()
        self._update_actions()
        self.pageChanged.emit(index, len(pages))

    def _update_page_combo(self, pages: List[int]):
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for page in sorted(set(pages) | {self.current_index}):
            self.page_combo.addItem(f"Page {page}", page)
        self.page_combo.setCurrentIndex(self.page_combo.findData(self.current_index))
        self.page_combo.blockSignals(False)

    def _update_empty_hint(self):
        if not self.working_objects:
            self.page_preview_widget.set_empty_hint(
                f"This device has no .jsonl files.\nAdd one to {self.device_pages_data.device.path} to create pages."
            )
        elif count_objects(self.working_objects) == 0:
            self.page_preview_widget.set_empty_hint("This device has no objects yet.", show_add_button=True)
        elif not any(obj.get("page") == self.current_index for obj in self.page_objects):
            self.page_preview_widget.set_empty_hint(f"Page {self.current_index} is empty.", show_add_button=True)
        else:
            self.page_preview_widget.set_empty_hint(None)

    def _mark_dirty(self):
        self.session.is_dirty = True
        self.dirtyChanged.emit(True)

    def _reload_page(self, select: List[Dict] = ()):
        """Rebuilds the preview from the draft after objects were added or removed, and selects the given objects."""
        self.set_page_index(self.current_index)
        for obj in select:
            for item in self.page_preview_widget.editable_items():
                if item.obj_data is obj:
                    item.setSelected(True)
        self.page_preview_widget.setFocus()

    # --- page navigation ---

    def _go_to_page(self, index: int):
        self.set_page_index(index)
        if self.action_sync.isChecked():
            self._sync_device_page(index)

    def _step_page(self, step: int):
        pages = get_navigable_page_indices(self.working_objects)
        if not pages:
            return
        if self.current_index in pages:
            new_index = pages[(pages.index(self.current_index) + step) % len(pages)]
        else:
            new_index = pages[0]
        self._go_to_page(new_index)

    @qBridge()
    def _on_previous_page_clicked(self):
        if self.session is not None:
            self._step_page(-1)

    @qBridge()
    def _on_next_page_clicked(self):
        if self.session is not None:
            self._step_page(1)

    def go_to_home_page(self):
        pages = get_navigable_page_indices(self.working_objects)
        if pages:
            self._go_to_page(pages[0])

    @qBridge(dict)
    def __on_preview_layout_button_clicked(self, obj: dict):
        LOGGER.debug(f"Clicked on object in preview: {obj}")
        action = obj.get("action", None)
        if action == "next":
            self._step_page(1)
        elif action == "prev":
            self._step_page(-1)
        elif action == "back":
            self.go_to_home_page()

    # --- editing ---

    def set_edit_mode(self, enabled: bool):
        self.action_edit_mode.setChecked(enabled)

    def _on_edit_mode_toggled(self, enabled: bool):
        self.page_preview_widget.set_mode(PreviewMode.Edit if enabled else PreviewMode.Interact)

    @qBridge(PreviewMode)
    def _on_editor_mode_changed(self, mode: PreviewMode):
        edit = mode == PreviewMode.Edit
        self.action_edit_mode.setChecked(edit)
        self.widget_picker.setVisible(edit)
        self.property_editor.set_edit_mode(edit)
        self._update_actions()

    @qBridge(list)
    def _on_openhasp_widget_selection_changed(self, editable_widgets: List[EditableWidget]):
        self.property_editor.set_editable_widgets(editable_widgets)
        self._update_actions()

    def _on_property_changed(self, _widget: EditableWidget, _key: str, _value: Any):
        self._mark_dirty()
        self.jsonl_preview.set_objects(self.page_objects)

    def _validate_property(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        if key == "id" and is_id_used(self.working_objects, obj.get("page"), value, ignore=obj):
            return f"Id {value} is already used on page {obj.get('page')}."
        return None

    def _on_items_moved(self, items: List[EditableWidget]):
        for item in items:
            item.obj_data["x"] = item.live_x
            item.obj_data["y"] = item.live_y
        self._after_geometry_edit()

    def nudge_selected_objects(self, dx: int, dy: int):
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        for item in items:
            item.obj_data["x"] = item.obj_x + dx
            item.obj_data["y"] = item.obj_y + dy
            item.setPos(float(item.obj_x), float(item.obj_y))
        self._after_geometry_edit()

    def _after_geometry_edit(self):
        self._mark_dirty()
        self.jsonl_preview.set_objects(self.page_objects)
        self.property_editor.refresh()

    def add_object(self, widget_type: OpenHASPWidgetType):
        component = find_target_component(self.working_objects, self.current_index)
        if component is None:
            return
        if not self.edit_mode:
            self.action_edit_mode.setChecked(True)

        screen = self.device_pages_data.device.config.openhasp_config_manager.device.screen
        obj = create_object(
            widget_type,
            page=self.current_index,
            obj_id=next_free_id(self.working_objects, self.current_index),
            screen_width=screen.width,
            screen_height=screen.height,
        )
        add_object(self.working_objects, component, obj)
        self._mark_dirty()
        self._reload_page(select=[obj])

    def duplicate_selected_objects(self):
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        duplicates = [duplicate_object(self.working_objects, item.obj_data) for item in items]
        self._mark_dirty()
        self._reload_page(select=duplicates)

    def remove_selected_objects(self):
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        names = ", ".join(f"p{item.obj_data.get('page')}b{item.obj_id}" for item in items)
        answer = QMessageBox.question(
            self,
            "Remove objects" if len(items) > 1 else "Remove object",
            f"Remove {names} from the page?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        for item in items:
            remove_object(self.working_objects, item.obj_data)
        self._mark_dirty()
        self._reload_page()

    # --- device ---

    @qBridge(bool)
    def _on_sync_with_real_device_toggled(self, enabled: bool):
        if enabled and self.session is not None:
            self._sync_device_page(self.current_index)

    def _sync_device_page(self, index: int):
        device = self.device_pages_data.device
        client = OpenHaspClient(device)
        description = f"Switching {device.name} to page {index}"
        run_busy(
            client.set_page(index),
            busy=self.busy,
            status=self.status,
            description=description,
            success_message=f"{device.name} shows page {index}",
            on_error=lambda ex: self.error_banner.show_error(
                f"{description} failed: {error_text(ex)}", retry=lambda: self._sync_device_page(index)
            ),
        )

    @qBridge()
    def _on_clear_page_clicked(self):
        device = self.device_pages_data.device
        index = self.current_index
        answer = QMessageBox.question(
            self,
            "Clear page",
            f"Clear page {index} on {device.name}?\n\nThis removes all objects of the page from the device "
            f"until the page is deployed again. The draft in the editor is not changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._clear_page(index)

    def _clear_page(self, index: int):
        device = self.device_pages_data.device
        client = OpenHaspClient(device)
        description = f"Clearing page {index} on {device.name}"
        self.error_banner.hide()
        run_busy(
            client.clear_page(index),
            busy=self.busy,
            status=self.status,
            description=description,
            success_message=f"Cleared page {index} on {device.name}",
            # the page on the device is empty now, the draft is not
            on_success=lambda _: self.pageOutOfSync.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._clear_page(index)),
        )

    @qBridge()
    def _on_deploy_page_clicked(self):
        self._deploy_page(self.current_index)

    def _deploy_page(self, index: int):
        """
        Clear the given page on the device and send all of its objects (including the global ones of page 0).
        """
        device = self.device_pages_data.device
        page_objects = get_page_objects(self.working_objects, index=index, include_global=True)
        if not page_objects:
            return

        client = OpenHaspClient(device)
        status = self.status
        description = f"Deploying page {index} to {device.name}"
        self.error_banner.hide()

        async def __async_work():
            await client.clear_page(index)
            for sent, obj in enumerate(page_objects, start=1):
                await client.jsonl(obj)
                status.report_progress(sent, len(page_objects))
                await asyncio.sleep(DEPLOY_DELAY_SECONDS)

        run_busy(
            __async_work(),
            busy=self.busy,
            status=status,
            description=description,
            success_message=f"Deployed page {index} to {device.name} ({len(page_objects)} objects)",
            on_success=lambda _: self.pageDeployed.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._deploy_page(index)),
        )

    def _on_send_failed(self, index: int, description: str, ex: Exception, retry: Callable[[], None]):
        self.pageOutOfSync.emit(index)
        self.error_banner.show_error(f"{description} failed: {error_text(ex)}", retry=retry)

    def resync_page(self, index: int):
        """Show the given page and deploy it, to bring the device back in sync with the draft."""
        if self.session is None:
            return
        self._go_to_page(index)
        self._deploy_page(index)
