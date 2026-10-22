import logging
import time
from enum import Enum, StrEnum
from typing import List, Optional, Dict, Callable, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QCursor, QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QApplication, QGraphicsView, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.ripple import Ripple, active_ripples
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.theme import current_colors
from openhasp_config_manager.gui.qt.async_bridge import qBridge
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.slider import HaspSliderItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.plate_scene import PlateScene
from openhasp_config_manager.openhasp_client.icons import IntegratedIcon

LOGGER = logging.getLogger(__name__)

DEFAULT_SCREEN_WIDTH = 480
DEFAULT_SCREEN_HEIGHT = 320

ZOOM_STEP = 1.25
MIN_ZOOM = 0.25
MAX_ZOOM = 8.0

# how long a message next to an object stays (see show_message)
MESSAGE_DURATION_MS = 6000


class PreviewMode(StrEnum):
    Interact = "interact"
    Edit = "edit"


class OverlayAnchor(Enum):
    """Where a floating bar sits on the preview (see `PagePreviewWidget.add_overlay`)."""

    TOP_RIGHT = "top_right"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


class PagePreviewWidget(QGraphicsView):
    """
    The plate preview: the page in the native resolution of the plate, scaled to fit the view (or zoomed),
    with the area around the plate in the canvas color.
    """

    modeChanged = QtCore.pyqtSignal(PreviewMode)
    buttonClicked = QtCore.pyqtSignal(dict)

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
        self._empty_hint: Optional[str] = None
        self._is_movable: Callable[[Dict], bool] = lambda _obj: True
        self._is_dimmed: Callable[[Dict], bool] = lambda _obj: False
        # where the mouse pressed on an object that can't be moved, until it is released
        self._locked_press: Optional[Tuple[QtCore.QPoint, EditableWidget]] = None

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
        if mode != PreviewMode.Edit:
            self.scene().clearSelection()
        for item in self.scene().items():
            if isinstance(item, EditableWidget):
                item.movable = mode == PreviewMode.Edit and self._is_movable(item.obj_data)
                item.editable = mode == PreviewMode.Edit
        self.viewport().update()
        self.modeChanged.emit(mode)

    def set_movable_predicate(self, is_movable: Callable[[Dict], bool]):
        """Decides which objects can be dragged in edit mode (others can still be selected)."""
        self._is_movable = is_movable

    def refresh_items(self):
        """Redraw all objects, e.g. after the edit of an object changed those with templates that refer to it."""
        for item in self.editable_items():
            item.refresh()
        self.refresh_movable()

    def refresh_movable(self):
        """Ask the movable predicate again, e.g. after the position of an object changed from a template to pixels."""
        for item in self.editable_items():
            item.movable = self.mode == PreviewMode.Edit and self._is_movable(item.obj_data)

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

    def set_objects(self, loaded_objects: List[dict]):
        self.objects = loaded_objects
        self.load_objects()
        self.viewport().update()

    def load_objects(self):
        self.scene().clear()
        for obj_data in self.objects:
            obj_type = obj_data.get("obj")
            if not obj_type:
                continue  # Skip objects with no type

            item = None
            if obj_type == "btn":
                item = self._create_button_widget(obj_data)
            elif obj_type == "switch":
                item = self._create_switch_widget(obj_data)
            elif obj_type == "bar":
                item = self._create_bar_widget(obj_data)
            elif obj_type == "slider":
                item = self._create_slider_widget(obj_data)
            elif obj_type == "label":
                item = self._create_label_widget(obj_data)
            elif obj_type == "img":
                item = self._create_img_widget(obj_data)

            if item is not None:
                LOGGER.debug(f"Adding '{obj_type}' item to scene: {item}")
                item.movable = self.mode == PreviewMode.Edit and self._is_movable(item.obj_data)
                item.editable = self.mode == PreviewMode.Edit
                item.set_dimmed(self._is_dimmed(item.obj_data))
                self.scene().addItem(item)

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

    def zoom_in(self):
        self._zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self._zoom_by(1 / ZOOM_STEP)

    def add_overlay(self, widget: QWidget, anchor: OverlayAnchor):
        """Show a widget (e.g. a toolbar) floating on the preview. The plate is fitted between the top and bottom ones."""
        widget.setParent(self.viewport())
        widget.show()
        self._overlays.append((widget, anchor))
        # never narrower than a bar: it would be cut off
        widest = max(overlay.sizeHint().width() for overlay, _anchor in self._overlays)
        self.setMinimumWidth(widest + 2 * UiDimensions.one + 2 * self.frameWidth())
        self._position_overlays()

    def fit_to_view(self):
        """Scale the plate to fill the view, with the rows of the floating bars above and below it kept free."""
        self._fit_to_view = True
        plate = self._padded_scene_rect()
        top, bottom = self._overlay_margins()
        viewport = self.viewport().rect()
        available_height = max(1, viewport.height() - top - bottom)
        scale = min(viewport.width() / plate.width(), available_height / plate.height())
        # the view shows the plate and the rows of the bars: fitting it centers the plate between them
        self.setSceneRect(plate.adjusted(0, -top / scale, 0, bottom / scale))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._position_add_object_button()

    def _overlay_margins(self) -> Tuple[int, int]:
        """:return: the height to keep free above and below the plate for the floating bars"""
        _positions, top, bottom = self._overlay_layout()
        return top, bottom

    def _position_overlays(self):
        positions, _top, _bottom = self._overlay_layout()
        for widget, position in positions.items():
            widget.move(position)

    def _overlay_layout(self) -> Tuple[Dict[QWidget, QtCore.QPoint], int, int]:
        """
        Where the floating bars go: the top right one in its corner, the bottom right one in its corner, and the bottom
        center one centered next to it, or in a row above it if they don't fit next to each other.
        :return: the position of each bar, and the height of the rows above and below the plate
        """
        margin = UiDimensions.one
        width = self.viewport().width()
        height = self.viewport().height()
        positions = {}
        top_row_bottom = 0
        bottom_row_top = height
        right_edge = width - margin
        visible = [(widget, anchor) for widget, anchor in self._overlays if not widget.isHidden()]
        for widget, anchor in visible:
            widget.adjustSize()
            x = max(margin, width - widget.width() - margin)
            if anchor == OverlayAnchor.TOP_RIGHT:
                positions[widget] = QtCore.QPoint(x, margin)
                top_row_bottom = max(top_row_bottom, margin + widget.height())
            elif anchor == OverlayAnchor.BOTTOM_RIGHT:
                y = height - widget.height() - margin
                positions[widget] = QtCore.QPoint(x, y)
                right_edge = min(right_edge, x - margin)
                bottom_row_top = min(bottom_row_top, y)
        last_row_top = bottom_row_top
        for widget, anchor in visible:
            if anchor == OverlayAnchor.BOTTOM_CENTER:
                x = min((width - widget.width()) // 2, right_edge - widget.width())
                y = height - widget.height() - margin
                if x < margin:
                    # no room next to the bar on the right: above it
                    x = max(margin, (width - widget.width()) // 2)
                    y = last_row_top - margin - widget.height()
                positions[widget] = QtCore.QPoint(x, y)
                bottom_row_top = min(bottom_row_top, y)
        top = top_row_bottom + margin if top_row_bottom else 0
        bottom = height - bottom_row_top + margin if bottom_row_top < height else 0
        return positions, top, bottom

    def _zoom_by(self, factor: float):
        current = self.transform().m11()
        factor = max(MIN_ZOOM, min(MAX_ZOOM, current * factor)) / current
        self._fit_to_view = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self._position_add_object_button()

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

    def mousePressEvent(self, event):
        self._add_ripple(event)
        self._message.hide()
        self._locked_press = None
        if self.mode == PreviewMode.Edit and event.button() == Qt.MouseButton.LeftButton:
            item = self._editable_item_at(event.position().toPoint())
            if item is not None and not item.movable:
                self._locked_press = (event.position().toPoint(), item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
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

    def drawForeground(self, painter: QPainter, rect: QRectF):
        self._draw_ripples(painter)

        plate = self.scene().sceneRect()

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

    def _on_button_clicked(self, obj_data: Dict):
        if self.mode != PreviewMode.Interact:
            return
        # Find the object data for this button
        if obj_data:
            self.buttonClicked.emit(obj_data)

    @qBridge()
    def _on_selection_changed(self):
        self.selectionChanged.emit(self.selected_items())

    @staticmethod
    def _replace_unicode_with_html(text: str, size: int) -> str:
        """
        Wraps icons in HTML font tags so they render with the correct MDI font
        while leaving regular text alone.
        """
        import qtawesome as qta

        processed_text = text

        # Get the actual font name qtawesome uses (usually 'Material Design Icons')
        mdi_font_family = qta.font("mdi6", size).family()

        for unicode_char, icon_name in IntegratedIcon.entries():
            if unicode_char in processed_text:
                icon_char = qta.charmap(f"mdi6.{icon_name}")
                # Wrap only the icon in a font tag
                replacement = f'<span style="font-family:{mdi_font_family};">{icon_char}</span>'
                processed_text = processed_text.replace(unicode_char, replacement)

        return f"<span>{processed_text}</span>"

    def _create_button_widget(self, obj_data: Dict) -> HaspButtonItem:
        return HaspButtonItem(
            obj_data=obj_data,
            on_click=self._on_button_clicked,
            parent_widget=self,
        )

    def _create_switch_widget(self, obj_data: Dict) -> HaspSwitchItem:
        widget = HaspSwitchItem(
            obj_data=obj_data,
            parent_widget=self,
        )
        widget.toggled.connect(lambda obj_id, val: LOGGER.debug(f"Switch {obj_id} toggled to {val}"))
        return widget

    def _create_bar_widget(self, obj_data: Dict) -> HaspBarItem:
        return HaspBarItem(
            obj_data=obj_data,
            parent_widget=self,
        )

    def _create_slider_widget(self, obj_data) -> HaspSliderItem:
        widget = HaspSliderItem(
            obj_data=obj_data,
            parent_widget=self,
        )
        widget.valueChanged.connect(lambda obj_id, val: LOGGER.debug(f"Slider {obj_id} changed to {val}"))
        return widget

    def _create_label_widget(self, obj_data: Dict) -> HaspLabelItem:
        return HaspLabelItem(
            obj_data=obj_data,
            parent_widget=self,
        )

    def _create_img_widget(self, obj_data: Dict) -> HaspImageItem:
        return HaspImageItem(
            obj_data=obj_data,
            parent_widget=self,
        )
