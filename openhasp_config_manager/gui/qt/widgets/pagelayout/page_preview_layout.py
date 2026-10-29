import logging
import time
from enum import StrEnum
from pathlib import Path
from typing import List, Optional, Dict, Callable, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QBrush, QCursor, QPainter, QPainterPath, QColor, QPen, QFont
from PyQt6.QtWidgets import QApplication, QGraphicsView, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.interaction import Indev, Point, RuntimeState, is_clickable, object_key
from openhasp_config_manager.gui.domain.preview_images import find_image_file
from openhasp_config_manager.gui.domain.ripple import Ripple, active_ripples
from openhasp_config_manager.gui.domain.tabs import tab_of
from openhasp_config_manager.gui.domain.touch_actions import object_command
from openhasp_config_manager.gui.domain.touch_groups import group_values
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.theme import current_colors
from openhasp_config_manager.gui.qt.async_bridge import qBridge
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.registry import ITEM_CLASSES
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import set_font_files
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.tabview import HaspTabviewItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.plate_scene import PlateScene
from openhasp_config_manager.gui.qt.widgets.pagelayout.preview_overlays import OverlayAnchor, overlay_layout
from openhasp_config_manager.openhasp_client.icons import IntegratedIcon
from openhasp_config_manager.openhasp_client.model.device import Device

LOGGER = logging.getLogger(__name__)

DEFAULT_SCREEN_WIDTH = 480
DEFAULT_SCREEN_HEIGHT = 320

ZOOM_STEP = 1.25
MIN_ZOOM = 0.25
MAX_ZOOM = 8.0
# fitting the shown objects (see `set_focus`) zooms in at most this far: a small part stays recognizable as a part of the plate
FOCUS_MAX_ZOOM = 4.0
# the space around the shown objects when they are fitted, of their size
FOCUS_MARGIN = 0.15

# how long a message next to an object stays (see show_message)
MESSAGE_DURATION_MS = 6000
# how often the preview looks whether a finger rests on an object for a long press
TOUCH_TICK_MS = 50


class PreviewMode(StrEnum):
    Interact = "interact"
    Edit = "edit"


# the stripes over the parts of objects that are outside of the screen
OUTSIDE_COLOR = "#E53935"

# the opacity of black over the plate at the lowest brightness (and while the screen is off), 0..255
MAX_DARKNESS = 215


class PagePreviewWidget(QGraphicsView):
    """
    The plate preview: the page in the native resolution of the plate, scaled to fit the view (or zoomed),
    with the area around the plate in the canvas color.
    """

    modeChanged = QtCore.pyqtSignal(PreviewMode)
    # the scale of the plate changed (zoom buttons, wheel, fitting to the view)
    zoomChanged = QtCore.pyqtSignal(float)
    # whether the plate is fitted to the view (it is scaled again when the view changes its size)
    fitChanged = QtCore.pyqtSignal(bool)
    # a command that touching an object ran (the `action` of a button), e.g. `page next`
    commandRequested = QtCore.pyqtSignal(str)

    # Emitted when the selection changes in edit mode, with the selected EditableWidgets
    selectionChanged = QtCore.pyqtSignal(list)

    # Emitted when the user dropped dragged objects, with the EditableWidgets whose position changed
    itemsMoved = QtCore.pyqtSignal(list)

    addObjectRequested = QtCore.pyqtSignal()

    # Emitted once per drag when the user tries to drag an object that can't be moved (see set_movable_predicate)
    lockedDragAttempted = QtCore.pyqtSignal(list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = PreviewMode.Interact
        self.objects: List[dict] = []
        self._fit_to_view = True
        self._image_files: Dict[str, Path] = {}
        # how much of the plate is darkened to simulate a lower backlight, 0..255
        self._darkness = 0
        self._empty_hint: Optional[str] = None
        self._is_movable: Callable[[Dict], bool] = lambda _obj: True
        self._is_selectable: Callable[[Dict], bool] = lambda _obj: True
        self._is_dimmed: Callable[[Dict], bool] = lambda _obj: False
        # the objects that are shown, the others are hidden; None: all of them (see `set_focus`)
        self._is_shown: Optional[Callable[[Dict], bool]] = None
        # where the mouse pressed on an object that can't be moved, until it is released
        self._locked_press: Optional[Tuple[QtCore.QPoint, EditableWidget]] = None

        # what touching the objects changed in interact mode: the draft is never changed by it (see RuntimeState)
        self.runtime = RuntimeState()
        self._indev = Indev(self._touch_target)
        # a finger that rests on an object long-presses it
        self._touch_timer = QtCore.QTimer(self)
        self._touch_timer.setInterval(TOUCH_TICK_MS)
        self._touch_timer.timeout.connect(lambda: self._indev.tick(time.monotonic()))
        # all objects of the plate, for the groups that reach over pages (the objects of the page by default)
        self._group_objects: Callable[[], List[Dict]] = lambda: self.objects

        # click feedback in interact mode, painted in drawForeground (not as scene items: reloading a page clears the scene)
        self._ripples: List[Ripple] = []
        self._ripple_timer = QtCore.QTimer(self)
        self._ripple_timer.setInterval(16)
        self._ripple_timer.timeout.connect(self._on_ripple_tick)

        # Make it scale smoothly
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 220)

        scene = PlateScene(self)
        scene.setSceneRect(0, 0, DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT)
        scene.selectionChanged.connect(self._on_selection_changed)
        self.setScene(scene)

        # shown on top of the empty plate, e.g. for a device without any objects
        self._add_object_button = UiComponents.create_button(
            title="Add object",
            icon="plus",
            on_click=self.addObjectRequested.emit,
        )
        self._add_object_button.setParent(self.viewport())
        self._add_object_button.hide()

        # a message next to an object, e.g. why it can't be dragged
        self._message = UiComponents.create_label("", word_wrap=True)
        self._message.setProperty("role", "floating")
        self._message.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        self._message.setMaximumWidth(360)
        self._message.setParent(self.viewport())
        self._message.hide()
        self._message_timer = QtCore.QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._message.hide)

        # floating bars on the preview: fitting the plate keeps their rows free
        self._overlays: List[Tuple[QWidget, OverlayAnchor]] = []

    def scene(self) -> PlateScene:
        return super().scene()

    def set_screen_brightness(self, brightness: int, on: bool = True):
        """
        Darken the plate like the backlight does, to see how the page looks at that brightness.
        :param brightness: 1..100
        """
        self._darkness = round(MAX_DARKNESS * (100 - brightness) / 100) if on else MAX_DARKNESS
        self.viewport().update()

    def set_image_files(self, files: Dict[str, Path]):
        """:param files: the image files of the device: their name on the plate -> the file, see `image_file`"""
        self._image_files = files

    def set_font_files(self, files: Dict[str, Path]):
        """:param files: the font files of the device (`.ttf`, and `.bin` files, which can be fonts): their name on the plate -> the file"""
        set_font_files(files)

    def image_file(self, src: str) -> Optional[Path]:
        """:return: the file the `src` of an object means, if the device has it"""
        return find_image_file(src, self._image_files)

    def set_device(self, device: Device):
        """Show the plate of a device: its screen size, images and fonts."""
        screen = device.config.openhasp_config_manager.device.screen
        self.set_screen_size(screen.width, screen.height)
        self.set_image_files({image.name: image.path for image in device.images})
        self.set_font_files(
            {font.name: font.path for font in [*device.fonts, *device.images] if font.name.endswith((".ttf", ".bin"))}
        )

    def set_screen_size(self, width: int, height: int):
        self.scene().setSceneRect(0, 0, width, height)
        self.fit_to_view()

    def set_mode(self, mode: PreviewMode):
        """
        Set the mode of the preview (interact or edit).
        In interact mode, buttons will emit signals when clicked.
        In edit mode, buttons will be selectable, movable resizable.

        :param mode: the mode to set
        """
        self.mode = mode
        if mode == PreviewMode.Edit:
            # the draft is shown again, not what touching the objects changed
            self.reset_interactions()
        else:
            self.scene().clearSelection()
        for item in self.scene().items():
            if isinstance(item, EditableWidget):
                item.movable = mode == PreviewMode.Edit and self._is_movable(item.obj_data)
                item.editable = mode == PreviewMode.Edit and self._is_selectable(item.obj_data)
        self.viewport().update()
        self.modeChanged.emit(mode)

    def set_movable_predicate(self, is_movable: Callable[[Dict], bool]):
        """Decides which objects can be dragged in edit mode (others can still be selected)."""
        self._is_movable = is_movable

    def set_selectable_predicate(self, is_selectable: Callable[[Dict], bool]):
        """Decides which objects can be selected in edit mode (e.g. in part mode only those of the part)."""
        self._is_selectable = is_selectable

    def refresh_items(self):
        """Redraw all objects, e.g. after the edit of an object changed those with templates that refer to it."""
        for item in self.editable_items():
            item.refresh()
        # a `parentid` may have changed
        self._nest_items()
        self.refresh_movable()

    def refresh_movable(self):
        """
        Ask the movable and selectable predicates again, e.g. after the position of an object changed from a template to
        pixels. Objects that can't be selected anymore are deselected.
        """
        for item in self.editable_items():
            item.movable = self.mode == PreviewMode.Edit and self._is_movable(item.obj_data)
            item.editable = self.mode == PreviewMode.Edit and self._is_selectable(item.obj_data)
            if not item.editable and item.isSelected():
                item.setSelected(False)

    def set_snap_enabled(self, enabled: bool):
        self.scene().snap_enabled = enabled
        self.viewport().update()

    def set_empty_hint(self, hint: Optional[str], show_add_button: bool = False):
        """
        :param hint: the text shown on the plate, or None if the page has objects
        :param show_add_button: whether to show an "Add object" button below it
        """
        self._empty_hint = hint
        self._add_object_button.setVisible(hint is not None and show_add_button)
        self._position_add_object_button()
        self.viewport().update()

    def set_dimmed_predicate(self, is_dimmed: Callable[[Dict], bool]):
        """Which objects to dim, e.g. those that are not in the file highlighted in the file tree."""
        self._is_dimmed = is_dimmed
        for item in self.editable_items():
            item.set_dimmed(is_dimmed(item.obj_data))

    def set_focus(self, is_shown: Optional[Callable[[Dict], bool]]):
        """
        Show only some of the objects (e.g. those of an instance of a part), and fit those to the view instead of the plate
        (see `fit_to_view`); None shows all of them again.
        """
        self._is_shown = is_shown
        self._apply_focus()
        self.viewport().update()

    @property
    def is_focused(self) -> bool:
        """Whether only some of the objects are shown (see `set_focus`)."""
        return self._is_shown is not None

    def _apply_focus(self):
        items = self.editable_items()
        shown = {id(item) for item in items if self._is_shown is None or self._is_shown(item.obj_data)}
        # the tabview of a shown object on one of its tabs stays, or the object would be hidden with it
        for item in items:
            if id(item) in shown:
                parent = item.parentItem()
                while parent is not None:
                    shown.add(id(parent))
                    parent = parent.parentItem()
        for item in items:
            item.set_shown(id(item) in shown)

    def _focus_rect(self) -> Optional[QRectF]:
        """:return: the area of the plate the shown objects cover (see `set_focus`), None if all objects are shown or none"""
        if self._is_shown is None:
            return None
        rect = QRectF()
        for item in self.editable_items():
            if item.isVisible() and self._is_shown(item.obj_data):
                rect = rect.united(item.mapRectToScene(item.obj_rect))
        return None if rect.isEmpty() else rect

    def set_objects(self, loaded_objects: List[dict]):
        self.objects = loaded_objects
        self.load_objects()
        self.viewport().update()

    def set_group_objects(self, provider: Callable[[], List[Dict]]):
        """
        Where to find the objects of all pages, for objects in a group (`groupid`) that follow each other over pages, and objects that
        commands change.
        """
        self._group_objects = provider

    def reset_interactions(self):
        """Forget what touching the objects changed: they show the draft again."""
        self._touch_timer.stop()
        self._indev.cancel()
        self.runtime.clear()
        for item in self.editable_items():
            item.refresh()
        self.viewport().update()

    def run_command(self, command: str):
        """Run a command of an `action`. After the mouse event: a command can change the page, which clears the scene."""
        QtCore.QTimer.singleShot(0, lambda: self._run_command(command))

    def _run_command(self, command: str):
        """A command that sets a property of an object (`p1b2.val 1`) changes it like a touch does, on any page."""
        target = object_command(command)
        if target is not None:
            obj = next(
                (obj for obj in self._group_objects() if obj.get("page") == target.page and obj.get("id") == target.id), None
            )
            # the plate warns about an object that doesn't exist
            if obj is not None:
                key = object_key(obj)
                self.runtime.set(key, target.attribute, target.value, obj)
                for item in self.editable_items():
                    if item.key == key:
                        item.runtime_changed()
        self.commandRequested.emit(command)

    def follow_group(self, source: EditableWidget, power: bool, value: int, minimum: int, maximum: int):
        """The objects in the group of an object that changed take its value, on every page (`event_update_group`)."""
        objects = self._group_objects()
        values = group_values(objects, source.obj_data, power, value, minimum, maximum)
        by_key = {object_key(obj): obj for obj in objects}
        for key, member_value in values.items():
            self.runtime.set(key, "val", member_value, by_key[key])
        for item in self.editable_items():
            if item.key in values:
                item.runtime_changed()

    def _touch_target(self, point: Point) -> Optional[EditableWidget]:
        """:return: the object a finger at a point of the plate presses: the topmost that is clickable (`lv_indev_search_obj`)"""
        scene_point = QtCore.QPointF(*point)
        for item in self.scene().items(Qt.SortOrder.DescendingOrder):
            if isinstance(item, EditableWidget) and item.isVisible() and is_clickable(item.data):
                local = item.mapFromScene(scene_point)
                # an object on a tab is only there where the tab is (`lv_indev_search_obj` only looks inside of the parent)
                if item.isClipped() and not item.clipPath().contains(local):
                    continue
                if item.hit(local):
                    return item
        return None

    def load_objects(self):
        # the items the finger was on are gone
        self._indev.forget()
        self.runtime.pressed, self.runtime.pressed_part = None, None
        # first, in one go: clearing the scene deselects the items one by one, and the selection would report items whose
        # objects are not in the draft anymore (e.g. after removing several objects)
        self.scene().clearSelection()
        self.scene().clear()
        for obj_data in self.objects:
            obj_type = obj_data.get("obj")
            if not obj_type:
                continue  # Skip objects with no type

            item = None
            if obj_type == "btn":
                item = HaspButtonItem(obj_data=obj_data, parent_widget=self)
            elif obj_type in ITEM_CLASSES:
                item = ITEM_CLASSES[obj_type](obj_data=obj_data, parent_widget=self)

            if item is not None:
                LOGGER.debug(f"Adding '{obj_type}' item to scene: {item}")
                item.movable = self.mode == PreviewMode.Edit and self._is_movable(item.obj_data)
                item.editable = self.mode == PreviewMode.Edit and self._is_selectable(item.obj_data)
                item.set_dimmed(self._is_dimmed(item.obj_data))
                self.scene().addItem(item)
        self._nest_items()
        self._apply_focus()

    def _nest_items(self):
        """Put the items of the objects on a tab on the page of the tab in its tabview: `x`/`y` are relative to it."""
        items = {item.key: item for item in self.editable_items()}
        for item in items.values():
            tab = tab_of(self.objects, item.obj_data)
            tabview = None if tab is None else items.get((tab.get("page"), tab.get("parentid")))
            page = tabview.tab_page(tab) if isinstance(tabview, HaspTabviewItem) else None
            if item.parentItem() is not page:
                item.setParentItem(page)

    def editable_items(self) -> List[EditableWidget]:
        return [item for item in self.scene().items() if isinstance(item, EditableWidget)]

    def selected_items(self) -> List[EditableWidget]:
        return [item for item in self.scene().selectedItems() if isinstance(item, EditableWidget)]

    def select_object(self, obj_data: Dict):
        self.scene().clearSelection()
        for item in self.editable_items():
            if item.obj_data is obj_data:
                item.setSelected(True)

    def cursor_plate_position(self) -> Optional[Tuple[int, int]]:
        """
        :return: the point of the plate under the mouse (on the grid while snapping is on), or None if the mouse isn't
            over the plate (or over one of the floating bars)
        """
        if QApplication.widgetAt(QCursor.pos()) is not self.viewport():
            return None
        point = self.mapToScene(self.viewport().mapFromGlobal(QCursor.pos()))
        if not self.scene().sceneRect().contains(point):
            return None
        if self.scene().snap_enabled:
            grid = self.scene().grid_size
            return round(point.x() / grid) * grid, round(point.y() / grid) * grid
        return int(point.x()), int(point.y())

    # --- zoom ---

    def _set_fit(self, fit: bool):
        if fit != self._fit_to_view:
            self._fit_to_view = fit
            self.fitChanged.emit(fit)

    def set_fit(self, fit: bool):
        """Fit the plate to the view and keep it fitted, or keep the current zoom."""
        if fit:
            self.fit_to_view()
        else:
            self._set_fit(False)

    @property
    def fits_to_view(self) -> bool:
        return self._fit_to_view

    def zoom(self) -> float:
        """:return: the scale of the plate (1.0: one pixel of the plate per pixel on the screen)"""
        return self.transform().m11()

    def set_zoom(self, zoom: float):
        """Zoom to a scale, around the center of the view."""
        self._set_fit(False)
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(zoom / self.zoom(), zoom / self.zoom())
        self._position_add_object_button()
        self.zoomChanged.emit(self.zoom())

    def zoom_in(self):
        self._zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self._zoom_by(1 / ZOOM_STEP)

    def add_overlay(self, widget: QWidget, anchor: OverlayAnchor):
        """Show a widget (e.g. a toolbar) floating on the preview. The plate is fitted between the top and bottom ones."""
        widget.setParent(self.viewport())
        widget.show()
        self._overlays.append((widget, anchor))
        self._update_minimum_width()
        self._position_overlays()

    def set_overlay_visible(self, widget: QWidget, visible: bool):
        """Show or hide a floating bar (see `add_overlay`)."""
        widget.setVisible(visible)
        self._update_minimum_width()
        self.update_overlays()

    def _update_minimum_width(self):
        # never narrower than a bar: it would be cut off
        widest = max((overlay.sizeHint().width() for overlay, _anchor in self._overlays if not overlay.isHidden()), default=0)
        self.setMinimumWidth(widest + 2 * UiDimensions.one + 2 * self.frameWidth())

    def update_overlays(self):
        """Place the floating bars again after one changed its size or visibility."""
        if self._fit_to_view:
            self.fit_to_view()
        self._position_overlays()

    def fit_to_view(self):
        """
        Scale the plate to fill the view, with the rows of the floating bars above and below it kept free. With a focus (see
        `set_focus`) the shown objects fill it instead.
        """
        self._set_fit(True)
        plate = self._padded_scene_rect()
        top, bottom = self._overlay_margins()
        viewport = self.viewport().rect()
        available_height = max(1, viewport.height() - top - bottom)
        focus = self._focus_rect()
        if focus is not None:
            self._fit_rect(focus, top, bottom)
        else:
            scale = min(viewport.width() / plate.width(), available_height / plate.height())
            # the view shows the plate and the rows of the bars: fitting it centers the plate between them
            self.setSceneRect(plate.adjusted(0, -top / scale, 0, bottom / scale))
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._position_add_object_button()
        self.zoomChanged.emit(self.zoom())

    def _fit_rect(self, rect: QRectF, top: int, bottom: int):
        """Scale an area of the plate to fill the view between the rows of the floating bars, at most `FOCUS_MAX_ZOOM`."""
        margin = max(rect.width(), rect.height()) * FOCUS_MARGIN + UiDimensions.one
        rect = rect.adjusted(-margin, -margin, margin, margin)
        viewport = self.viewport().rect()
        available_height = max(1, viewport.height() - top - bottom)
        scale = min(viewport.width() / rect.width(), available_height / rect.height(), FOCUS_MAX_ZOOM)
        # what the view shows, in the plate: the area centered between the bars (like the plate, see `fit_to_view`)
        visible = QRectF(0, 0, viewport.width() / scale, viewport.height() / scale)
        visible.moveCenter(rect.center() + QtCore.QPointF(0, (bottom - top) / (2 * scale)))
        self.setSceneRect(visible)
        self.fitInView(visible, Qt.AspectRatioMode.KeepAspectRatio)

    def _overlay_margins(self) -> Tuple[int, int]:
        """:return: the height to keep free above and below the plate for the floating bars"""
        _positions, top, bottom = overlay_layout(self._overlays, self.viewport().width(), self.viewport().height())
        return top, bottom

    def _position_overlays(self):
        positions, _top, _bottom = overlay_layout(self._overlays, self.viewport().width(), self.viewport().height())
        for widget, position in positions.items():
            widget.move(position)

    def _zoom_by(self, factor: float):
        current = self.transform().m11()
        factor = max(MIN_ZOOM, min(MAX_ZOOM, current * factor)) / current
        self._set_fit(False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self._position_add_object_button()
        self.zoomChanged.emit(self.zoom())

    def _padded_scene_rect(self) -> QRectF:
        margin = UiDimensions.two
        return self.scene().sceneRect().adjusted(-margin, -margin, margin, margin)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_by(ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP)
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()
        if self._fit_to_view:
            self.fit_to_view()
        self._position_add_object_button()

    def _plate_point(self, event) -> Point:
        """:return: where a mouse event is on the plate, kept on the screen (a finger can't leave it)"""
        position = self.mapToScene(event.position().toPoint())
        plate = self.scene().sceneRect()
        return min(max(position.x(), plate.left()), plate.right() - 1), min(max(position.y(), plate.top()), plate.bottom() - 1)

    def finger(self, point: Point, now: float):
        """The finger is at a point of the plate (pressing, or moving while it presses)."""
        if not self._indev.is_pressing:
            self._close_list_unless_touched(point)
        self._indev.press(point, now)

    def _close_list_unless_touched(self, point: Point):
        """A new press somewhere else than on the open list of a dropdown closes it (the dropdown loses the focus), the value stays."""
        key = self.runtime.open_dropdown
        if key is None:
            return
        target = self._touch_target(point)
        if target is None or target.key != key:
            self.runtime.open_dropdown = None
            for item in self.editable_items():
                if item.key == key:
                    item.runtime_changed()

    def _touch(self, event):
        """The mouse presses or drags in interact mode: it is a finger on the plate."""
        if not self._indev.is_pressing and not self.scene().sceneRect().contains(self.mapToScene(event.position().toPoint())):
            return
        self.finger(self._plate_point(event), time.monotonic())
        self._touch_timer.start()
        self.viewport().update()

    def mousePressEvent(self, event):
        self._add_ripple(event)
        self._message.hide()
        self._locked_press = None
        if self.mode == PreviewMode.Interact and event.button() == Qt.MouseButton.LeftButton:
            self._touch(event)
            event.accept()
            return
        if self.mode == PreviewMode.Edit and event.button() == Qt.MouseButton.LeftButton:
            item = self._editable_item_at(event.position().toPoint())
            if item is not None and not item.movable:
                self._locked_press = (event.position().toPoint(), item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._indev.is_pressing:
            self._touch(event)
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self._locked_press is None:
            return
        start, item = self._locked_press
        if (event.position().toPoint() - start).manhattanLength() >= QApplication.startDragDistance():
            self._locked_press = None
            self.viewport().setCursor(Qt.CursorShape.ForbiddenCursor)
            self.lockedDragAttempted.emit([item])

    def show_message(self, text: str, near: EditableWidget):
        """Show a message below an object (above it, if there is no room), until the next click or MESSAGE_DURATION_MS."""
        self._message.setText(text)
        self._message.adjustSize()
        viewport = self.viewport().rect()
        rect = self.mapFromScene(near.sceneBoundingRect()).boundingRect()
        margin = UiDimensions.half
        y = rect.bottom() + margin
        if y + self._message.height() > viewport.bottom():
            y = rect.top() - margin - self._message.height()
        x = min(max(rect.left(), margin), viewport.right() - self._message.width() - margin)
        self._message.move(x, max(y, margin))
        self._message.show()
        self._message.raise_()
        self._message_timer.start(MESSAGE_DURATION_MS)

    def _editable_item_at(self, point: QtCore.QPoint) -> Optional[EditableWidget]:
        """:return: the object under a point of the viewport (also when a child item of it, e.g. its text, is there)"""
        item = self.itemAt(point)
        while item is not None and not isinstance(item, EditableWidget):
            item = item.parentItem()
        return item

    def mouseDoubleClickEvent(self, event):
        # the second press of a fast double click arrives here instead of in mousePressEvent
        if self.mode == PreviewMode.Interact:
            self.mousePressEvent(event)
            return
        self._add_ripple(event)
        super().mouseDoubleClickEvent(event)

    def _add_ripple(self, event):
        if self.mode == PreviewMode.Interact and event.button() == Qt.MouseButton.LeftButton:
            position = self.mapToScene(event.position().toPoint())
            if self.scene().sceneRect().contains(position):
                self._ripples.append(Ripple(x=position.x(), y=position.y(), started=time.monotonic()))
                self._ripple_timer.start()

    def _on_ripple_tick(self):
        self._ripples = active_ripples(self._ripples, time.monotonic())
        if not self._ripples:
            self._ripple_timer.stop()
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        if self._indev.is_pressing and event.button() == Qt.MouseButton.LeftButton:
            self._touch_timer.stop()
            self._indev.release(self._plate_point(event))
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._locked_press = None
        self.viewport().unsetCursor()
        self.scene().clear_guides()
        if self.mode != PreviewMode.Edit:
            return
        moved = [item for item in self.selected_items() if item.movable and (item.delta_x != 0 or item.delta_y != 0)]
        if moved:
            self.itemsMoved.emit(moved)

    # --- painting ---

    def drawBackground(self, painter: QPainter, rect: QRectF):
        colors = current_colors()
        painter.fillRect(rect, QColor(colors.canvas))

        plate = self.scene().sceneRect()
        painter.fillRect(plate, QColor("black"))

        if self.mode == PreviewMode.Edit and self.scene().snap_enabled:
            self._draw_grid(painter, plate)

    def _draw_grid(self, painter: QPainter, plate: QRectF):
        grid = self.scene().grid_size
        # skip the grid if its points would be closer than 4 pixels on screen
        if grid * self.transform().m11() < 4:
            return
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidth(0)  # cosmetic: 1 screen pixel
        painter.setPen(pen)
        x = plate.left()
        while x <= plate.right():
            y = plate.top()
            while y <= plate.bottom():
                painter.drawPoint(QtCore.QPointF(x, y))
                y += grid
            x += grid

    def _draw_outside_plate(self, painter: QPainter, plate: QRectF):
        """Mark the parts of the objects that are outside of the screen with red stripes: the plate doesn't show them."""
        screen = QPainterPath()
        screen.addRect(plate)
        outside = QPainterPath()
        for item in self.editable_items():
            if item.isVisible():
                outside.addRect(item.mapRectToScene(item.obj_rect))
        outside = outside.subtracted(screen)
        if outside.isEmpty():
            return
        red = QColor(OUTSIDE_COLOR)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        red.setAlpha(70)
        painter.setBrush(red)
        painter.drawPath(outside)
        painter.setBrush(QBrush(QColor(OUTSIDE_COLOR), Qt.BrushStyle.BDiagPattern))
        painter.drawPath(outside)
        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF):
        plate = self.scene().sceneRect()
        if self._darkness:
            painter.fillRect(plate, QColor(0, 0, 0, self._darkness))

        self._draw_ripples(painter)
        self._draw_outside_plate(painter, plate)

        guides_x, guides_y = self.scene().guides_x, self.scene().guides_y
        if guides_x or guides_y:
            pen = QPen(QColor(current_colors().accent))
            pen.setWidth(0)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for x in guides_x:
                painter.drawLine(QtCore.QLineF(x, plate.top(), x, plate.bottom()))
            for y in guides_y:
                painter.drawLine(QtCore.QLineF(plate.left(), y, plate.right(), y))

        if self._empty_hint:
            painter.setPen(QColor(255, 255, 255, 150))
            font = QFont(painter.font())
            font.setPixelSize(max(12, int(plate.height() / 20)))
            painter.setFont(font)
            text_rect = plate.adjusted(plate.width() * 0.1, 0, -plate.width() * 0.1, -plate.height() * 0.15)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._empty_hint,
            )

    def _draw_ripples(self, painter: QPainter):
        now = time.monotonic()
        # the ripples have a size on screen, the painter works in scene coordinates
        scale = self.transform().m11()
        color = QColor(255, 255, 255)
        for ripple in self._ripples:
            radius = ripple.radius(now) / scale
            color.setAlphaF(0.5 * ripple.opacity(now))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QtCore.QPointF(ripple.x, ripple.y), radius, radius)

    def _position_add_object_button(self):
        if self._add_object_button.isHidden():
            return
        plate = self.mapFromScene(self.scene().sceneRect()).boundingRect()
        size = self._add_object_button.sizeHint()
        self._add_object_button.move(
            plate.center().x() - size.width() // 2,
            plate.top() + int(plate.height() * 0.7),
        )

    # --- items ---

    @qBridge()
    def _on_selection_changed(self):
        self.selectionChanged.emit(self.selected_items())

    @staticmethod
    def _replace_unicode_with_html(text: str, size: int) -> str:
        """
        Wraps icons in HTML font tags so they render with the correct MDI font
        while leaving regular text alone.
        """
        import html

        import qtawesome as qta

        processed_text = html.escape(text).replace("\n", "<br/>")

        # Get the actual font name qtawesome uses (usually 'Material Design Icons')
        mdi_font_family = qta.font("mdi6", size).family()

        for unicode_char, icon_name in IntegratedIcon.entries():
            if unicode_char in processed_text:
                icon_char = qta.charmap(f"mdi6.{icon_name}")
                # Wrap only the icon in a font tag
                replacement = f'<span style="font-family:{mdi_font_family};">{icon_char}</span>'
                processed_text = processed_text.replace(unicode_char, replacement)

        return f"<span>{processed_text}</span>"
