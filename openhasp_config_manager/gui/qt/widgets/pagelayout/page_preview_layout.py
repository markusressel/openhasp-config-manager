import logging
from enum import StrEnum
from typing import List, Optional, Dict

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QGraphicsView

from openhasp_config_manager.gui.dimensions import UiDimensions
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


class PreviewMode(StrEnum):
    Interact = "interact"
    Edit = "edit"


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = PreviewMode.Interact
        self.objects: List[dict] = []
        self._fit_to_view = True
        self._empty_hint: Optional[str] = None

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
                item.movable = mode == PreviewMode.Edit
                item.editable = mode == PreviewMode.Edit
        self.viewport().update()
        self.modeChanged.emit(mode)

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
                item.movable = self.mode == PreviewMode.Edit
                item.editable = self.mode == PreviewMode.Edit
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

    # --- zoom ---

    def zoom_in(self):
        self._zoom_by(ZOOM_STEP)

    def zoom_out(self):
        self._zoom_by(1 / ZOOM_STEP)

    def fit_to_view(self):
        self._fit_to_view = True
        self.fitInView(self._padded_scene_rect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._position_add_object_button()

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
        if self._fit_to_view:
            self.fit_to_view()
        self._position_add_object_button()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.scene().clear_guides()
        if self.mode != PreviewMode.Edit:
            return
        moved = [item for item in self.selected_items() if item.delta_x != 0 or item.delta_y != 0]
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
