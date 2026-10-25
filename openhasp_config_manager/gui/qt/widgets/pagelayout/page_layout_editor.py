import asyncio
import copy
import logging
import math
from collections import OrderedDict
from typing import List, Dict, Optional, Any, Callable, Set, Tuple

from PyQt6 import QtCore
from jinja2 import TemplateError
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QSlider, QWidget, QToolBar, QComboBox, QMessageBox, QToolButton, QFrame, QHBoxLayout

from openhasp_config_manager.gui.domain.problems import Problem, find_problems
from openhasp_config_manager.gui.domain.tabs import last_tabview_id
from openhasp_config_manager.gui.domain.page_objects import (
    OpenHASPWidgetType,
    get_page_objects,
    get_navigable_page_indices,
    count_objects,
    next_free_id,
    is_id_used,
    create_object,
    step_page,
)
from openhasp_config_manager.gui.domain.clipboard import PasteCascade, objects_from_text, objects_to_text, with_descendants
from openhasp_config_manager.gui.domain.file_tree import default_target_component, relative_config_path
from openhasp_config_manager.gui.domain.live_preview import LivePage
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.domain.ui_session import DeviceSession
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.layouts import frozen
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, run_busy, error_text
from openhasp_config_manager.gui.qt.async_bridge import qBridge, run_async
from openhasp_config_manager.gui.qt.throttle import LatestValueThrottle
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.widgets.device_controls import DeviceControlsWidget
from openhasp_config_manager.gui.qt.widgets.message_panel import ErrorBanner
from openhasp_config_manager.gui.qt.widgets.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.problems_panel import ProblemsPanel
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_picker import OpenHASPWidgetPicker
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widget_property_editor import OpenHASPWidgetPropertyEditor
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import (
    MAX_ZOOM,
    MIN_ZOOM,
    OverlayAnchor,
    PagePreviewWidget,
    PreviewMode,
)
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

LOGGER = logging.getLogger(__name__)

# delay between two objects when sending a whole page, to avoid overwhelming the device
SEND_DELAY_SECONDS = 0.1
# Live preview sends the changes of the draft at most this often, e.g. while dragging an object
LIVE_PREVIEW_INTERVAL_MS = 50

LOCKED_POSITION_HINT = "the position is a template or a percentage: use pixels for x/y in the properties to move it"
LOCKED_POSITION_FIX = "To move it, use pixels for x/y in the properties: this replaces the template or percentage."

RESTORE_PLATE_HINT = "Values sent by haad or Home Assistant appear again with their next update."

NUDGE_STEP = 1
NUDGE_STEP_LARGE = 10


# the positions of the zoom slider
ZOOM_SLIDER_STEPS = 100


class PageLayoutEditorWidget(QWidget):
    """
    The page layout editor: the plate preview with the widget picker, and the editor actions in `toolbar`.
    The property editor (`property_editor`) and the JSONL view (`jsonl_preview`) belong to it,
    but are placed by the main window.
    """

    # (current page index, number of navigable pages)
    pageChanged = QtCore.pyqtSignal(int, int)
    dirtyChanged = QtCore.pyqtSignal(bool)
    # a page on the device may differ from what it should show: sending it failed, or it was cleared
    pageOutOfSync = QtCore.pyqtSignal(int)
    pageDeployed = QtCore.pyqtSignal(int)
    # the plate shows its own files again
    plateRestored = QtCore.pyqtSignal()
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
        # what is wrong with the objects on the page
        self.problems: List[Problem] = []
        self._paste_cascade = PasteCascade()

        # Live preview: what the plate shows of the current page, and the changes of the draft that wait to be sent
        self._live_page = LivePage()
        self._live_throttle = LatestValueThrottle(
            lambda _: self._send_live_changes(), interval_ms=LIVE_PREVIEW_INTERVAL_MS, parent=self
        )
        self._stopping_live_preview_silently = False
        # keeps what is sent to the plate in order: a page that is sent in full, then the changes after it
        self._send_lock = asyncio.Lock()

        # remote control of the selected plate; the preview shows its brightness
        self.device_controls = DeviceControlsWidget(status=status)
        # what is wrong with the objects of the page
        self.problems_panel = ProblemsPanel()

        self.property_editor = OpenHASPWidgetPropertyEditor()
        self.property_editor.removeObjectClicked.connect(self.remove_selected_objects)
        self.property_editor.duplicateObjectClicked.connect(self.duplicate_selected_objects)
        self.property_editor.usePixelPositionClicked.connect(self.use_pixel_positions)
        self.property_editor.propertyChanged.connect(self._on_property_changed)
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
        self.widget_picker.addItem.connect(self.add_object)
        row.addWidget(self.widget_picker)

        column = UiComponents.create_column()
        row.addLayout(column, 1)

        self.error_banner = ErrorBanner()
        column.addWidget(self.error_banner)

        self.page_preview_widget = PagePreviewWidget()
        self.page_preview_widget.set_movable_predicate(lambda obj: self.session is None or self._is_movable(obj))
        self.page_preview_widget.buttonClicked.connect(self.__on_preview_layout_button_clicked)
        self.page_preview_widget.modeChanged.connect(self._on_editor_mode_changed)
        self.page_preview_widget.selectionChanged.connect(self._on_openhasp_widget_selection_changed)
        self.page_preview_widget.itemsMoved.connect(self._on_items_moved)
        self.page_preview_widget.lockedDragAttempted.connect(self._report_locked)
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
            self, "Duplicate", "content-duplicate", self.duplicate_selected_objects, shortcut="Ctrl+D", context=canvas
        )
        self.action_delete = create(self, "Remove", "delete", self.remove_selected_objects, shortcut="Del", context=canvas)
        self.action_copy = create(
            self, "Copy", "content-copy", self.copy_selected_objects, shortcut=QKeySequence.StandardKey.Copy, context=canvas
        )
        self.action_paste = create(
            self,
            "Paste",
            "content-paste",
            self.paste_objects,
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

        self.action_live_preview = create(
            self,
            "Live preview",
            "broadcast",
            tooltip="Show the draft on the plate while you edit it: the page of the editor and every change are sent "
            "right away.\nNothing is stored on the plate: Restore plate or a restart brings back its files.",
            checkable=True,
        )
        self.action_live_preview.toggled.connect(self._on_live_preview_toggled)
        self.action_clear = create(
            self,
            "Clear page",
            "eraser",
            self._on_clear_page_clicked,
            tooltip="Remove all objects of the page from the plate, until Restore plate or Live preview fills it again",
        )
        self.action_restore_plate = create(
            self,
            "Restore plate",
            "backup-restore",
            self._on_restore_plate_clicked,
            tooltip="Show what the files on the plate define, like after a restart.\n" + RESTORE_PLATE_HINT,
        )

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
                        lambda dx=dx, dy=dy, step=step: self.nudge_selected_objects(dx * step, dy * step),
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

        self.toolbar.addAction(self.action_live_preview)
        self.toolbar.addAction(self.action_clear)
        self.toolbar.addAction(self.action_restore_plate)

        preview = self.page_preview_widget
        preview.add_overlay(self._floating_bar([self.device_controls]), OverlayAnchor.TOP_LEFT)
        preview.add_overlay(self.problems_panel, OverlayAnchor.BOTTOM_LEFT)
        preview.add_overlay(
            self._floating_bar(
                [self.action_edit_mode, self.action_snap, None, self.action_duplicate, self.action_delete],
                with_text=[self.action_edit_mode, self.action_snap],
            ),
            OverlayAnchor.TOP_RIGHT,
        )
        preview.add_overlay(
            self._floating_bar([self.action_previous_page, self.page_combo, self.action_next_page]),
            OverlayAnchor.BOTTOM_CENTER,
        )
        preview.add_overlay(
            self._floating_bar([self.action_zoom_out, self._create_zoom_slider(), self.action_zoom_in, self.action_zoom_fit]),
            OverlayAnchor.BOTTOM_RIGHT,
        )

    def _on_fit_changed(self, fit: bool):
        self.action_zoom_fit.blockSignals(True)
        self.action_zoom_fit.setChecked(fit)
        self.action_zoom_fit.blockSignals(False)

    def _create_zoom_slider(self) -> QSlider:
        """A slider for the zoom of the preview, on a logarithmic scale: every step zooms by the same factor."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, ZOOM_SLIDER_STEPS)
        slider.setFixedWidth(UiDimensions.five * 4)
        slider.setToolTip("Zoom of the preview")
        # keep the keyboard focus on the plate, for its shortcuts
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        preview = self.page_preview_widget

        def on_moved(position: int):
            preview.set_zoom(MIN_ZOOM * (MAX_ZOOM / MIN_ZOOM) ** (position / ZOOM_SLIDER_STEPS))

        def on_zoom_changed(zoom: float):
            # the zoom changed by other means: only move the handle
            slider.blockSignals(True)
            slider.setValue(round(ZOOM_SLIDER_STEPS * math.log(zoom / MIN_ZOOM) / math.log(MAX_ZOOM / MIN_ZOOM)))
            slider.blockSignals(False)

        slider.valueChanged.connect(on_moved)
        preview.zoomChanged.connect(on_zoom_changed)
        self.zoom_slider = slider
        return slider

    @staticmethod
    def _floating_bar(items: List[Optional[QAction | QWidget]], with_text: List[QAction] = ()) -> QFrame:
        """
        A small toolbar that floats on the preview.
        :param items: actions (shown as buttons), widgets, and None for a separator
        :param with_text: the actions that show their text next to the icon
        """
        bar = QFrame()
        bar.setProperty("role", "floating")
        row = QHBoxLayout(bar)
        row.setContentsMargins(UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half)
        row.setSpacing(UiDimensions.half)
        for item in items:
            if item is None:
                separator = QFrame()
                separator.setFrameShape(QFrame.Shape.VLine)
                separator.setFrameShadow(QFrame.Shadow.Sunken)
                row.addWidget(separator)
            elif isinstance(item, QAction):
                button = QToolButton()
                button.setDefaultAction(item)
                button.setAutoRaise(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                # keep the keyboard focus on the plate, for its shortcuts
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextBesideIcon if item in with_text else Qt.ToolButtonStyle.ToolButtonIconOnly
                )
                row.addWidget(button)
            else:
                row.addWidget(item)
        return bar

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
            self.action_live_preview,
        ]:
            action.setEnabled(has_data)
        self.zoom_slider.setEnabled(has_data)
        self.page_combo.setEnabled(has_data and self.page_combo.count() > 1)
        self.action_previous_page.setEnabled(can_navigate)
        self.action_next_page.setEnabled(can_navigate)
        self.action_duplicate.setEnabled(self.edit_mode and has_selection)
        self.action_delete.setEnabled(self.edit_mode and has_selection)
        self.action_copy.setEnabled(self.edit_mode and has_selection)
        self.action_paste.setEnabled(has_data)
        # while Live preview is on, the page on the plate follows the draft
        self.action_clear.setEnabled(has_data and not busy and not self.live_preview)
        self.action_restore_plate.setEnabled(has_data and not busy)
        self.widget_picker.setEnabled(has_data and len(self.working_objects) > 0)

    # --- data ---

    def clear(self):
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
        self.session = session
        self.device_pages_data = device_pages_data
        self.error_banner.hide()
        self.highlight_component(None)
        self.property_editor.set_session(session)

        screen = device_pages_data.device.config.openhasp_config_manager.device.screen
        self.page_preview_widget.set_screen_size(screen.width, screen.height)

        pages = get_navigable_page_indices(self.working_objects)
        if page is None or (pages and page not in pages):
            page = pages[0] if pages else 1
        self.set_page_index(page)
        self.dirtyChanged.emit(self.session.is_dirty)
        # e.g. the draft was reverted: show the reloaded objects
        self._schedule_live_changes()

    def set_page_index(self, index: int):
        LOGGER.debug(f"Setting page index {index}")
        self.current_index = index
        self.page_objects = get_page_objects(self.working_objects, index=index)
        self.page_preview_widget.set_objects(self.page_objects)
        self._update_page_views()
        self.property_editor.set_editable_widgets([])

        pages = get_navigable_page_indices(self.working_objects)
        self._update_page_combo(pages)
        self._update_empty_hint()
        self._update_actions()
        self.pageChanged.emit(index, len(pages))
        self.fileStateChanged.emit()

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
        """Report a change of the draft (the session marks itself dirty)."""
        self.dirtyChanged.emit(self.session.is_dirty)
        self.fileStateChanged.emit()
        self._schedule_live_changes()

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
        if self.live_preview:
            self._start_live_page(index)

    def _step_page(self, step: int):
        new_index = step_page(get_navigable_page_indices(self.working_objects), self.current_index, step)
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
        self.stateChanged.emit()

    @qBridge(list)
    def _on_openhasp_widget_selection_changed(self, editable_widgets: List[EditableWidget]):
        self.property_editor.set_editable_widgets(editable_widgets)
        self.jsonl_preview.set_selected_objects([widget.obj_data for widget in editable_widgets])
        self._update_actions()
        self.stateChanged.emit()
        if len(editable_widgets) == 1:
            key = self.session.component_of(editable_widgets[0].obj_data).key
            if self._highlighted_component not in (None, key):
                # the object of another file was selected: the highlight would not match the file tree anymore
                self.highlight_component(None)
            self.selectedObjectComponentChanged.emit(key)
        else:
            self.selectedObjectComponentChanged.emit(None)

    def _update_page_views(self):
        """Update what is derived from the objects of the page: the JSONL and the problems."""
        self.jsonl_preview.set_objects(self.page_objects)
        screen = self.device_pages_data.device.config.openhasp_config_manager.device.screen
        self.problems = find_problems(self.page_objects, screen.width, screen.height)
        self.problems_panel.set_problems(self.problems)
        self.stateChanged.emit()

    def _on_property_changed(self, _widget: EditableWidget, _key: str, _value: Any):
        self.page_preview_widget.refresh_items()
        self._mark_dirty()
        self._update_page_views()

    def _validate_property(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        if key == "id" and is_id_used(self.working_objects, obj.get("page"), value, ignore=obj):
            return f"Id {value} is already used on page {obj.get('page')}."
        return None

    def _is_movable(self, obj: Dict) -> bool:
        """Objects whose position is a template or a percentage can't be dragged: it would replace them with pixels."""
        return not self.session.has_computed_position(obj)

    def _report_locked(self, items: List[EditableWidget]):
        """Explain why objects can't be moved: in the status bar, and next to the first of them."""
        names = ", ".join(f"p{item.obj_data.get('page')}b{item.obj_id}" for item in items)
        self.status.failed.emit(f"Moving {names}", LOCKED_POSITION_HINT)
        first = items[0]
        reasons = "\n".join(self.session.computed_position_reasons(first.obj_data))
        name = f"p{first.obj_data.get('page')}b{first.obj_id}"
        self.page_preview_widget.show_message(f"{name} can't be moved:\n{reasons}\n{LOCKED_POSITION_FIX}", near=first)

    def use_pixel_positions(self):
        """Replace the templates and percentages in x and y of the selected objects with pixels, so they can be moved."""
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        for item in items:
            self.session.use_pixel_position(item.obj_data)
        self.page_preview_widget.refresh_movable()
        self._after_geometry_edit()

    def _on_items_moved(self, items: List[EditableWidget]):
        for item in items:
            self._move(item, item.live_x, item.live_y)
        self._after_geometry_edit()

    def nudge_selected_objects(self, dx: int, dy: int):
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        locked = [item for item in items if not self._is_movable(item.obj_data)]
        if locked:
            self._report_locked(locked)
        for item in items:
            if item not in locked:
                self._move(item, item.obj_x + dx, item.obj_y + dy)
        self._after_geometry_edit()

    def _move(self, item: EditableWidget, x: int, y: int):
        self.session.set_source_value(item.obj_data, "x", x)
        self.session.set_source_value(item.obj_data, "y", y)
        item.refresh()

    def _after_geometry_edit(self):
        self.page_preview_widget.refresh_items()
        self._mark_dirty()
        self._update_page_views()
        self.property_editor.refresh()

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

        def is_dimmed(obj) -> bool:
            return key is not None and self.session.component_of(obj).key != key

        self.page_preview_widget.set_dimmed_predicate(is_dimmed)
        self.jsonl_preview.set_dimmed_predicate(is_dimmed)

    def add_object(self, widget_type: OpenHASPWidgetType):
        component = self.target_component
        if component is None:
            return
        if not self.edit_mode:
            self.action_edit_mode.setChecked(True)

        parent_id = self._parent_for(widget_type)
        if widget_type == OpenHASPWidgetType.TAB and parent_id is None:
            self.status.failed.emit("Adding a tab", "A tab belongs to a tabview: add a tabview to this page first")
            return
        try:
            obj_id = next_free_id(self.working_objects, self.current_index)
        except ValueError as ex:
            self.status.failed.emit(f"Adding a {widget_type}", error_text(ex))
            return
        screen = self.device_pages_data.device.config.openhasp_config_manager.device.screen
        obj = create_object(
            widget_type,
            page=self.current_index,
            obj_id=obj_id,
            screen_width=screen.width,
            screen_height=screen.height,
            parent_id=parent_id,
        )
        obj = self.session.add_object(component, obj)
        self._mark_dirty()
        self._reload_page(select=[obj])

    def _parent_for(self, widget_type: OpenHASPWidgetType) -> Optional[int]:
        """The object a new object belongs to: a tab goes into the last tabview of the page."""
        if widget_type != OpenHASPWidgetType.TAB:
            return None
        objects = [obj for objects in self.working_objects.values() for obj in objects]
        return last_tabview_id(objects, self.current_index)

    def duplicate_selected_objects(self):
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        duplicates = []
        for item in items:
            try:
                duplicates.append(self.session.duplicate_object(item.obj_data))
            except ValueError as ex:
                self.status.failed.emit(f"Duplicating p{item.obj_data.get('page')}b{item.obj_id}", error_text(ex))
                break
        self._mark_dirty()
        self._reload_page(select=duplicates)

    def copy_selected_objects(self):
        """Copy the selected objects (with the objects inside of them) to the clipboard, as JSONL with their templates."""
        items = self.page_preview_widget.selected_items()
        if not self.edit_mode or not items:
            return
        objects = with_descendants(self.page_objects, [item.obj_data for item in items])
        QApplication.clipboard().setText(objects_to_text([self.session.source_of(obj) for obj in objects]))
        self._paste_cascade.reset()

    def paste_objects(self):
        """
        Paste the objects of the clipboard into the file for new objects: where the mouse is, if it is over the plate,
        otherwise next to the originals. Pasting again to the same spot moves the copies a bit further each time.
        """
        component = self.target_component
        if component is None:
            return
        text = QApplication.clipboard().text()
        sources = objects_from_text(text)
        if not sources:
            self.status.failed.emit("Pasting", "the clipboard holds no openHASP objects (JSONL)")
            return
        if not self.edit_mode:
            self.action_edit_mode.setChecked(True)

        screen = self.device_pages_data.device.config.openhasp_config_manager.device.screen
        position = self.page_preview_widget.cursor_plate_position()
        try:
            pasted = self.session.paste_objects(
                component,
                sources,
                page=self.current_index,
                screen=(screen.width, screen.height),
                position=position,
                offset=self._paste_cascade.next_offset(text, position),
            )
        except (ValueError, TemplateError) as ex:
            self.status.failed.emit("Pasting", error_text(ex))
            return
        self._mark_dirty()
        self._reload_page(select=pasted)

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
            self.session.remove_object(item.obj_data)
        self._mark_dirty()
        self._reload_page()

    # --- plate ---

    @property
    def live_preview(self) -> bool:
        return self.action_live_preview.isChecked()

    def stop_live_preview(self):
        """Turn Live preview off without offering to restore the plate, e.g. when another device is selected."""
        self._stopping_live_preview_silently = True
        try:
            self.action_live_preview.setChecked(False)
        finally:
            self._stopping_live_preview_silently = False

    @qBridge(bool)
    def _on_live_preview_toggled(self, enabled: bool):
        self._update_actions()
        self.stateChanged.emit()
        if self.session is None:
            return
        if enabled:
            self._start_live_page(self.current_index)
            return
        self._live_throttle.cancel()
        if self._stopping_live_preview_silently:
            return

        device = self.device_pages_data.device
        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Live preview off",
            f"{device.name} still shows the draft of the editor.\n\n"
            f"Restore the plate, to show what its files define, like after a restart? {RESTORE_PLATE_HINT}",
            parent=self,
        )
        restore = box.addButton("Restore plate", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep the draft", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(restore)
        box.exec()
        if box.clickedButton() is restore:
            self.restore_plate()

    def _start_live_page(self, index: int):
        """Show the page on the plate with the objects of the draft."""
        objects = get_page_objects(self.working_objects, index=index, include_global=True)
        self._live_page.reset(objects)
        self._send_page(index, objects, show=True)

    def _schedule_live_changes(self):
        if self.live_preview:
            self._live_throttle.push(None)

    def _send_live_changes(self):
        """Send what changed in the draft since the page was last sent."""
        if self.session is None or not self.live_preview:
            return
        index = self.current_index
        objects = get_page_objects(self.working_objects, index=index, include_global=True)
        update = self._live_page.update(objects)
        if update is None:
            return
        if update.resend_page:
            self._send_page(index, objects, show=False)
            return

        device = self.device_pages_data.device
        client = OpenHaspClient(device)
        description = f"Sending the changes of page {index} to {device.name}"

        async def __async_work():
            async with self._send_lock:
                for page, obj_id in update.deletions:
                    await client.delete_object_id(page, obj_id)
                for obj in update.objects:
                    await client.jsonl(obj)

        # not run_busy: disabling the editor would interrupt dragging
        run_async(
            __async_work(),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self.resync_page(index)),
        )

    def _send_page(self, index: int, objects: List[Dict], show: bool):
        """
        Clear the page on the plate and send the given objects (including the global ones of page 0).
        :param show: switch the plate to the page afterwards
        """
        device = self.device_pages_data.device
        # the editor changes the objects in place, while they are being sent
        objects = copy.deepcopy(objects)
        client = OpenHaspClient(device)
        status = self.status
        description = f"Sending page {index} to {device.name}"
        self.error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                await client.clear_page(index)
                for sent, obj in enumerate(objects, start=1):
                    await client.jsonl(obj)
                    status.report_progress(sent, len(objects))
                    await asyncio.sleep(SEND_DELAY_SECONDS)
                if show:
                    await client.set_page(index)

        run_busy(
            __async_work(),
            busy=self.busy,
            status=status,
            description=description,
            success_message=f"{device.name} shows page {index} of the draft ({len(objects)} objects)",
            on_success=lambda _: self.pageDeployed.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self.resync_page(index)),
        )

    @qBridge()
    def _on_clear_page_clicked(self):
        device = self.device_pages_data.device
        index = self.current_index
        answer = QMessageBox.question(
            self,
            "Clear page",
            f"Clear page {index} on {device.name}?\n\nThis removes all objects of the page from the plate, "
            f"until Restore plate or Live preview fills it again. The draft in the editor is not changed.",
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
            # the page on the plate is empty now, its files are not
            on_success=lambda _: self.pageOutOfSync.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._clear_page(index)),
        )

    @qBridge()
    def _on_restore_plate_clicked(self):
        device = self.device_pages_data.device
        answer = QMessageBox.question(
            self,
            "Restore plate",
            f"Restore {device.name}?\n\nAll pages are cleared and built again from the files on the plate, "
            f"like after a restart. {RESTORE_PLATE_HINT}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_plate()

    def restore_plate(self):
        """Rebuild all pages of the plate from its own files, like after a restart (Live preview ends)."""
        self.stop_live_preview()
        device = self.device_pages_data.device
        client = OpenHaspClient(device)
        description = f"Restoring {device.name} from its files"
        self.error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                await client.restore_from_files()

        run_busy(
            __async_work(),
            busy=self.busy,
            status=self.status,
            description=description,
            success_message=f"{device.name} shows its files again",
            on_success=lambda _: self.plateRestored.emit(),
            on_error=lambda ex: self.error_banner.show_error(
                f"{description} failed: {error_text(ex)}", retry=self.restore_plate
            ),
        )

    def _on_send_failed(self, index: int, description: str, ex: Exception, retry: Callable[[], None]):
        self.pageOutOfSync.emit(index)
        self.error_banner.show_error(f"{description} failed: {error_text(ex)}", retry=retry)

    def resync_page(self, index: int):
        """
        Bring the plate back to what it should show: the page of the draft with Live preview, its files without.
        """
        if self.session is None:
            return
        if self.live_preview:
            self._go_to_page(index)
        else:
            self.restore_plate()
