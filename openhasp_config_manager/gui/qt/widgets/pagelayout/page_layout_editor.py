import logging
from collections import Counter, OrderedDict
from typing import List, Dict, Optional, Any, Callable, Set, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QWidget,
    QToolBar,
    QComboBox,
)

from openhasp_config_manager.gui.domain.problems import Problem, find_problems
from openhasp_config_manager.gui.domain.page_objects import (
    OpenHASPWidgetType,
    get_page_objects,
    get_navigable_page_indices,
    count_objects,
    is_id_used,
    navigate,
    page_label,
    selectable_pages,
    step_page,
)
from openhasp_config_manager.gui.domain.file_tree import default_target_component, relative_config_path
from openhasp_config_manager.gui.domain.draft_model import ChangeKind, DraftChange
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.domain.ui_session import DeviceSession
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.layouts import frozen
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus
from openhasp_config_manager.gui.qt.async_bridge import qBridge
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.widgets.device_controls import DeviceControlsWidget
from openhasp_config_manager.gui.qt.widgets.message_panel import ErrorBanner
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.problems_panel import ProblemsPanel
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_picker import OpenHASPWidgetPicker
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_property_editor import OpenHASPWidgetPropertyEditor
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.floating_bar import create_zoom_slider, floating_bar
from openhasp_config_manager.gui.qt.widgets.pagelayout.object_actions import ObjectActions
from openhasp_config_manager.gui.qt.widgets.pagelayout.plate_link import PlateLink
from openhasp_config_manager.gui.qt.widgets.pagelayout.preview_overlays import OverlayAnchor
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_indicator import PageIndicator
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import (
    PagePreviewWidget,
    PreviewMode,
)

LOGGER = logging.getLogger(__name__)

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
    # the pages of the files of the draft, the page or the target file changed (see `file_state`)
    fileStateChanged = QtCore.pyqtSignal()
    # the key of the component of the selected object, None if not exactly one object is selected
    selectedObjectComponentChanged = QtCore.pyqtSignal(object)
    # something the GUI state file reports changed (selection, mode, problems, ...)
    stateChanged = QtCore.pyqtSignal()

    def __init__(self, status: OperationStatus, ui_session: Optional[UiSessionStore] = None):
        """:param ui_session: where the choices of the user are remembered for the next start (in memory if None)"""
        super().__init__()
        self.status = status
        self.busy = BusyState(self)
        self.busy.changed.connect(lambda _: self._update_actions())

        self.session: Optional[PlateSession] = None
        self.device_pages_data: Optional[OpenHaspDevicePagesData] = None
        self.current_index = 1
        self.page_objects: List[Dict] = []
        self._ui_session = ui_session or UiSessionStore.in_memory()
        # the component whose objects are highlighted (the others are dimmed)
        self._highlighted_component: Optional[str] = None
        # the component of the selected object, None unless exactly one is selected: the JSONL dims the other files
        self._selected_component: Optional[str] = None
        # the component the JSONL shows undimmed (the others are dimmed), None if it dims nothing
        self._jsonl_dimmed_component: Optional[str] = None
        # what is wrong with the objects on the page
        self.problems: List[Problem] = []

        # remote control of the selected plate; the preview shows its brightness
        self.device_controls = DeviceControlsWidget(status=status)
        # what is wrong with the objects of the page
        self.problems_panel = ProblemsPanel()

        self.object_actions = ObjectActions(self)
        self.property_editor = OpenHASPWidgetPropertyEditor()
        self.property_editor.removeObjectClicked.connect(self.object_actions.remove_selected)
        self.property_editor.duplicateObjectClicked.connect(self.object_actions.duplicate_selected)
        self.property_editor.usePixelPositionClicked.connect(self.object_actions.use_pixel_positions)
        self.property_editor.set_validator(self._validate_property)

        self.jsonl_preview = PageJsonlPreviewWidget()

        self._create_layout()
        self._create_actions()
        self._create_toolbar()

        self.device_controls.screenChanged.connect(self.page_preview_widget.set_screen_brightness)
        self.problems_panel.layoutChanged.connect(self.page_preview_widget.update_overlays)
        self.problems_panel.problemClicked.connect(self.page_preview_widget.select_object)
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
        self.widget_picker.addItem.connect(self.object_actions.add)
        row.addWidget(self.widget_picker)

        column = UiComponents.create_column()
        row.addLayout(column, 1)

        self.error_banner = ErrorBanner()
        column.addWidget(self.error_banner)

        self.page_preview_widget = PagePreviewWidget()
        self.page_preview_widget.set_movable_predicate(lambda obj: self.session is None or self.object_actions.is_movable(obj))
        self.page_preview_widget.buttonClicked.connect(self.__on_preview_layout_button_clicked)
        self.page_preview_widget.modeChanged.connect(self._on_editor_mode_changed)
        self.page_preview_widget.selectionChanged.connect(self._on_openhasp_widget_selection_changed)
        self.page_preview_widget.itemsMoved.connect(self.object_actions.on_items_moved)
        self.page_preview_widget.lockedDragAttempted.connect(self.object_actions.report_locked)
        self.page_preview_widget.addObjectRequested.connect(lambda: self.object_actions.add(OpenHASPWidgetType.LABEL))
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
        self.page_indicator = PageIndicator()
        self.page_indicator.pageClicked.connect(self._go_to_page)

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

        # in the whole window: text fields handle the keys themselves while they have the focus
        self.action_undo = create(self, "Undo", "undo", self.undo, shortcut=QKeySequence.StandardKey.Undo)
        self.action_redo = create(self, "Redo", "redo", self.redo, shortcut=QKeySequence.StandardKey.Redo)
        self.action_duplicate = create(
            self, "Duplicate", "content-duplicate", self.object_actions.duplicate_selected, shortcut="Ctrl+D", context=canvas
        )
        self.action_delete = create(
            self, "Remove", "delete", self.object_actions.remove_selected, shortcut="Del", context=canvas
        )
        self.action_copy = create(
            self,
            "Copy",
            "content-copy",
            self.object_actions.copy_selected,
            shortcut=QKeySequence.StandardKey.Copy,
            context=canvas,
        )
        self.action_paste = create(
            self,
            "Paste",
            "content-paste",
            self.object_actions.paste,
            shortcut=QKeySequence.StandardKey.Paste,
            tooltip="Paste the copied objects where the mouse is, or next to the originals",
            context=canvas,
        )

        self.action_zoom_in = create(
            self, "Zoom in", "magnify-plus-outline", self.page_preview_widget.zoom_in, shortcut="Ctrl++"
        )
        self.action_zoom_out = create(
            self, "Zoom out", "magnify-minus-outline", self.page_preview_widget.zoom_out, shortcut="Ctrl+-"
        )
        # on while the zoom follows the size of the window: zooming turns it off
        self.action_zoom_fit = create(
            self,
            "Fit to window",
            "fit-to-screen-outline",
            shortcut="Ctrl+0",
            tooltip="Keep the whole plate in view as the window changes its size",
            checkable=True,
        )
        self.action_zoom_fit.setChecked(self.page_preview_widget.fits_to_view)
        self.action_zoom_fit.toggled.connect(self.page_preview_widget.set_fit)
        self.page_preview_widget.fitChanged.connect(self._on_fit_changed)

        # Live preview, Clear page and Restore plate
        self.plate = PlateLink(
            self,
            status=self.status,
            busy=self.busy,
            error_banner=self.error_banner,
            device=lambda: None if self.session is None else self.device_pages_data.device,
            page_objects=lambda index: get_page_objects(self.working_objects, index=index, include_global=True),
            current_page=lambda: self.current_index,
            resync=self.resync_page,
        )
        self.plate.liveChanged.connect(lambda _: self._update_actions())
        self.plate.liveChanged.connect(lambda _: self.stateChanged.emit())

        # keyboard only, while the preview has the focus
        canvas_actions = [
            self.action_delete,
            self.action_duplicate,
            self.action_copy,
            self.action_paste,
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
                        lambda dx=dx, dy=dy, step=step: self.object_actions.nudge_selected(dx * step, dy * step),
                        shortcut=f"{modifier}{key}",
                        context=canvas,
                    )
                )
        self.page_preview_widget.addActions(canvas_actions)

    def _create_toolbar(self):
        """
        The window toolbar has the actions for the plate. The editing, page and zoom controls float on the preview.
        """
        self.toolbar = QToolBar("Editor")
        self.toolbar.setObjectName("editor_toolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        self.toolbar.addWidget(spacer)

        self.toolbar.addAction(self.plate.action_live_preview)
        self.toolbar.addAction(self.plate.action_clear)
        self.toolbar.addAction(self.plate.action_restore_plate)

        preview = self.page_preview_widget
        self.zoom_slider = create_zoom_slider(preview)
        preview.add_overlay(floating_bar([self.device_controls]), OverlayAnchor.TOP_LEFT)
        preview.add_overlay(self.problems_panel, OverlayAnchor.BOTTOM_LEFT)
        preview.add_overlay(
            floating_bar(
                [
                    self.action_edit_mode,
                    self.action_snap,
                    None,
                    self.action_undo,
                    self.action_redo,
                    None,
                    self.action_duplicate,
                    self.action_delete,
                ],
                with_text=[self.action_edit_mode, self.action_snap],
            ),
            OverlayAnchor.TOP_RIGHT,
        )
        preview.add_overlay(
            floating_bar([self.action_previous_page, self.page_combo, self.action_next_page], footer=self.page_indicator),
            OverlayAnchor.BOTTOM_CENTER,
        )
        preview.add_overlay(
            floating_bar([self.action_zoom_out, self.zoom_slider, self.action_zoom_in, self.action_zoom_fit]),
            OverlayAnchor.BOTTOM_RIGHT,
        )

    def _on_fit_changed(self, fit: bool):
        self.action_zoom_fit.blockSignals(True)
        self.action_zoom_fit.setChecked(fit)
        self.action_zoom_fit.blockSignals(False)

    def _update_actions(self):
        has_data = self.session is not None
        has_selection = bool(self.page_preview_widget.selected_items())

        for action in [
            self.action_edit_mode,
            self.action_snap,
            self.action_zoom_in,
            self.action_zoom_out,
            self.action_zoom_fit,
        ]:
            action.setEnabled(has_data)
        self.zoom_slider.setEnabled(has_data)
        self.page_combo.setEnabled(has_data)
        self.action_previous_page.setEnabled(has_data)
        self.action_next_page.setEnabled(has_data)
        self.action_duplicate.setEnabled(self.edit_mode and has_selection)
        self.action_delete.setEnabled(self.edit_mode and has_selection)
        self.action_copy.setEnabled(self.edit_mode and has_selection)
        self.action_paste.setEnabled(has_data)
        self._update_undo_actions()
        self.plate.update_actions(has_data)
        self.widget_picker.setEnabled(has_data and len(self.working_objects) > 0)

    def _update_undo_actions(self):
        session = self.session
        for action, title, description in [
            (self.action_undo, "Undo", session and session.undo_description),
            (self.action_redo, "Redo", session and session.redo_description),
        ]:
            text = title if description is None else f"{title} {description}"
            action.setEnabled(description is not None)
            action.setText(text)
            action.setToolTip(f"{text} ({action.shortcut().toString()})")

    # --- data ---

    def clear(self):
        if self.session is not None:
            self.session.remove_listener(self._on_draft_changed)
        self.session = None
        self.device_pages_data = None
        self.current_index = 1
        self.page_objects = []
        self.page_preview_widget.set_objects([])
        self.jsonl_preview.set_objects([])
        self.problems_panel.set_problems([])
        self.error_banner.hide()
        self.problems = []
        self._update_actions()
        self.stateChanged.emit()

    def set_data(self, session: PlateSession, device_pages_data: OpenHaspDevicePagesData, page: Optional[int] = None):
        """
        :param session: the draft, loaded
        :param page: the page to show, defaults to the first one (also if the draft has no such page anymore)
        """
        if self.session is not None and self.session is not session:
            self.session.remove_listener(self._on_draft_changed)
        self.session = session
        session.add_listener(self._on_draft_changed)
        self.device_pages_data = device_pages_data
        self.error_banner.hide()
        self.highlight_component(None)
        self.property_editor.set_session(session)

        screen = device_pages_data.device.config.openhasp_config_manager.device.screen
        self.page_preview_widget.set_screen_size(screen.width, screen.height)
        self.page_preview_widget.set_image_files({image.name: image.path for image in device_pages_data.device.images})

        pages = get_navigable_page_indices(self.working_objects)
        if page is None or (pages and page not in pages):
            page = pages[0] if pages else 1
        self.set_page_index(page)
        self.dirtyChanged.emit(self.session.is_dirty)
        # e.g. the draft was reverted: show the reloaded objects
        self.plate.draft_changed()

    def set_page_index(self, index: int):
        LOGGER.debug(f"Setting page index {index}")
        self.current_index = index
        self.page_objects = get_page_objects(self.working_objects, index=index)
        self.page_preview_widget.set_objects(self.page_objects)
        self._update_page_views()
        self.property_editor.set_editable_widgets([])

        pages = get_navigable_page_indices(self.working_objects)
        self._update_page_combo()
        self._update_empty_hint()
        self._update_actions()
        self.pageChanged.emit(index, len(pages))
        self.fileStateChanged.emit()

    def _update_page_combo(self):
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for page in selectable_pages(self.current_index):
            self.page_combo.addItem(page_label(page), page)
        self.page_combo.setCurrentIndex(self.page_combo.findData(self.current_index))
        self.page_combo.blockSignals(False)
        counts = Counter(
            obj["page"] for objects in self.working_objects.values() for obj in objects if isinstance(obj.get("page"), int)
        )
        self.page_indicator.set_state(selectable_pages(self.current_index), self.current_index, dict(counts))

    def _update_empty_hint(self):
        if not self.working_objects:
            self.page_preview_widget.set_empty_hint(
                f"This device has no .jsonl files.\nAdd one to {self.device_pages_data.device.path} to create pages."
            )
        elif count_objects(self.working_objects) == 0:
            self.page_preview_widget.set_empty_hint("This device has no objects yet.", show_add_button=True)
        elif not any(obj.get("page") == self.current_index for obj in self.page_objects):
            what = "No object is on all pages." if self.current_index == 0 else f"Page {self.current_index} is empty."
            self.page_preview_widget.set_empty_hint(what, show_add_button=True)
        else:
            self.page_preview_widget.set_empty_hint(None)

    def _on_draft_changed(self, change: DraftChange):
        """Show a change of the draft: every edit, undo and redo ends here, wherever it was made."""
        if change.kind in (ChangeKind.UNDO, ChangeKind.REDO):
            self._show_undone(change)
        elif change.kind == ChangeKind.SAVE:
            pass
        elif change.adds_or_removes:
            self._reload_page(select=change.added)
        else:
            # objects with templates that refer to the changed ones may have changed too
            self.page_preview_widget.refresh_items()
            self._update_page_views()
            self.property_editor.refresh_after_change()
        self.dirtyChanged.emit(self.session.is_dirty)
        self.fileStateChanged.emit()
        self._update_undo_actions()
        self.plate.draft_changed()

    def _reload_page(self, select: List[Dict] = ()):
        """Rebuilds the preview from the draft after objects were added or removed, and selects the given objects."""
        with frozen(self):
            self.set_page_index(self.current_index)
            for obj in select:
                for item in self.page_preview_widget.editable_items():
                    if item.obj_data is obj:
                        item.setSelected(True)
        self.page_preview_widget.setFocus()

    # --- page navigation ---

    def _go_to_page(self, index: int):
        self.set_page_index(index)
        self.plate.show_page(index)

    def _step_page(self, step: int):
        # the pages of the dropdown, in its order
        new_index = step_page(selectable_pages(self.current_index), self.current_index, step)
        if new_index is not None:
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
        if action in ("next", "prev", "back"):
            # like on the plate: the settings of the page limit where the buttons lead (the toolbar can go to any page)
            start_page = self.device_pages_data.device.config.hasp.startpage
            target = navigate(self.working_objects, self.current_index, action, start_page)
            if target is not None:
                self._go_to_page(target)

    # --- undo ---

    def undo(self):
        if self.session is not None:
            self.session.undo()

    def redo(self):
        if self.session is not None:
            self.session.redo()

    def _show_undone(self, change: DraftChange):
        """Show what an undo or redo changed: on its page, with the changed objects selected."""
        pages = get_navigable_page_indices(self.working_objects)
        # the objects of page 0 are on every page
        shown = {self.current_index, 0}
        candidates = sorted(page for page in change.pages if isinstance(page, int) and page in pages)
        if not change.pages & shown and candidates:
            self._go_to_page(candidates[0])
            shown = {self.current_index, 0}
        self._reload_page(select=[obj for obj in change.objects if obj.get("page") in shown])
        done = "Undone" if change.kind == ChangeKind.UNDO else "Redone"
        self.status.succeeded.emit(f"{done}: {change.description}")

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
        self.stateChanged.emit()

    @qBridge(list)
    def _on_openhasp_widget_selection_changed(self, editable_widgets: List[EditableWidget]):
        self.property_editor.set_editable_widgets(editable_widgets)
        self.jsonl_preview.set_selected_objects([widget.obj_data for widget in editable_widgets])
        if self.session is not None:
            # e.g. typing into the same property of another object is another step
            self.session.end_merging()
        self._update_actions()
        self.stateChanged.emit()
        # the file of a single selected object is selected in the file tree (see `selectedObjectComponentChanged`)
        key = self.session.component_of(editable_widgets[0].obj_data).key if len(editable_widgets) == 1 else None
        self._selected_component = key
        if self._highlighted_component not in (None, key) and key is not None:
            # the object of another file was selected: the highlight would not match the file tree anymore
            self.highlight_component(None)
        else:
            self._update_jsonl_dimming()
        self.selectedObjectComponentChanged.emit(key)

    def _update_page_views(self):
        """Update what is derived from the objects of the page: the JSONL and the problems."""
        self.jsonl_preview.set_objects(self.page_objects)
        screen = self.device_pages_data.device.config.openhasp_config_manager.device.screen
        self.problems = find_problems(self.page_objects, screen.width, screen.height)
        self.problems_panel.set_problems(self.problems)
        self.stateChanged.emit()

    def _validate_property(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        if key == "id" and is_id_used(self.working_objects, obj.get("page"), value, ignore=obj):
            return f"Id {value} is already used on page {obj.get('page')}."
        return None

    # --- files ---

    @property
    def target_component(self) -> Optional[str]:
        """The key of the component new objects of the current page are added to: the one the user chose, or a default."""
        if self.session is None:
            return None
        chosen = self._device_ui_session().target_file
        for component in self.session.components:
            if relative_config_path(component.path, self.session.device.path) == chosen:
                return component.key
        return default_target_component(self.session.components, self.working_objects, self.current_index)

    def set_target_component(self, key: str):
        """Add new objects to this component (of the current device) from now on."""
        component = next(component for component in self.session.components if component.key == key)
        self._device_ui_session().target_file = relative_config_path(component.path, self.session.device.path)
        self._ui_session.save()
        self.fileStateChanged.emit()

    def _device_ui_session(self) -> DeviceSession:
        return self._ui_session.session.device(self.session.device.name)

    def file_state(self) -> Tuple[Dict[str, Set[int]], int, Optional[str]]:
        """:return: the pages each component has objects on, the current page, and the target component"""
        pages = {key: {obj.get("page") for obj in objects} for key, objects in self.working_objects.items()}
        return pages, self.current_index, self.target_component

    def highlight_component(self, key: Optional[str]):
        """Dim all objects that are not in the given component, or none (None)."""
        self._highlighted_component = key
        self.page_preview_widget.set_dimmed_predicate(self._outside_of(key))
        self._update_jsonl_dimming()

    def _update_jsonl_dimming(self):
        """
        The JSONL dims the lines of the other files: of the highlighted file, or else of the file of the selected objects. The
        preview dims nothing for a selection, the objects around the selected ones are needed to edit them.
        """
        key = self._highlighted_component or self._selected_component
        if key != self._jsonl_dimmed_component:
            self._jsonl_dimmed_component = key
            self.jsonl_preview.set_dimmed_predicate(self._outside_of(key))

    def _outside_of(self, key: Optional[str]) -> Callable[[Dict], bool]:
        """:return: whether an object is not in the component (False for all objects if None)"""
        return lambda obj: key is not None and self.session.component_of(obj).key != key

    # --- plate ---

    def resync_page(self, index: int):
        """
        Bring the plate back to what it should show: the page of the draft with Live preview, its files without.
        """
        if self.session is None:
            return
        if self.plate.live:
            self._go_to_page(index)
        else:
            self.plate.restore_plate()
