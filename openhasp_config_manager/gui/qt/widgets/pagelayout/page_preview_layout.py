import logging
from enum import StrEnum
from typing import List, Optional, Dict

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene

from openhasp_config_manager.gui.qt.util import qBridge
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.slider import HaspSliderItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import OpenHaspDevicePagesData
from openhasp_config_manager.openhasp_client.icons import IntegratedIcon


class PreviewMode(StrEnum):
    Interact = "interact"
    Edit = "edit"


class PagePreviewWidget(QGraphicsView):
    modeChanged = QtCore.pyqtSignal(PreviewMode)
    buttonClicked = QtCore.pyqtSignal(dict)

    # Emitted when the selection changes in edit mode, providing the currently selected object's data (or None if nothing is selected)
    selectionChanged = QtCore.pyqtSignal(list)

    @property
    def page_width(self) -> int:
        return self.data.device.config.openhasp_config_manager.device.screen.width

    @property
    def page_height(self) -> int:
        return self.data.device.config.openhasp_config_manager.device.screen.height

    def __init__(self, data: Optional[OpenHaspDevicePagesData] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = PreviewMode.Interact

        self.data: Optional[OpenHaspDevicePagesData] = data
        self.objects: List[dict] = []

        # Make it scale smoothly
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.set_data(data)

    def set_mode(self, mode: PreviewMode):
        """
        Set the mode of the preview (interact or edit).
        In interact mode, buttons will emit signals when clicked.
        In edit mode, buttons will be selectable, movable resizable.

        :param mode: the mode to set
        """
        self.mode = mode
        for item in self.scene().items():
            if isinstance(item, EditableWidget):
                item.movable = (mode == PreviewMode.Edit)
                item.editable = (mode == PreviewMode.Edit)

        self.modeChanged.emit(mode)

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
                logging.debug(f"Adding '{obj_type}' item to scene: {item}")
                self.scene().addItem(item)

    def _on_button_clicked(self, obj_data: Dict):
        if self.mode != PreviewMode.Interact:
            return
        # Find the object data for this button
        if obj_data:
            self.buttonClicked.emit(obj_data)

    def set_data(self, data: Optional[OpenHaspDevicePagesData]):
        self.data = data
        self._setup_scene(data)
        self.set_objects([])

    def _setup_scene(self, data: Optional[OpenHaspDevicePagesData]):
        native_width = 480
        native_height = 320
        if data is not None:
            # 1. Setup the Scene (use the device's actual native resolution)
            native_width = self.data.device.config.openhasp_config_manager.device.screen.width
            native_height = self.data.device.config.openhasp_config_manager.device.screen.height

        if self.scene() is None:
            scene = QGraphicsScene(0, 0, native_width, native_height)
            scene.setBackgroundBrush(QColor('black'))
            scene.selectionChanged.connect(self._on_selection_changed)
            self.setScene(scene)
        else:
            self.scene().clear()

    @qBridge()
    def _on_selection_changed(self):
        selected_items = self.scene().selectedItems()
        editable_widgets = [item for item in selected_items if isinstance(item, EditableWidget)]

        obj_data_list = [item.obj_data for item in editable_widgets]
        self.selectionChanged.emit(obj_data_list)

    def set_objects(self, loaded_objects: List[dict]):
        self.objects = loaded_objects
        self.load_objects()
        self._trigger_refresh()

    def _trigger_refresh(self):
        self.update()

    def resizeEvent(self, event):
        # This keeps the aspect ratio and fits the scene into the view
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        super().resizeEvent(event)

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

        return f'<span>{processed_text}</span>'

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
        widget.toggled.connect(lambda obj_id, val: print(f"Switch {obj_id} toggled to {val}"))
        return widget

    def _create_bar_widget(self, obj_data: Dict) -> HaspBarItem:
        return HaspBarItem(
            obj_data=obj_data,
            parent_widget=self
        )

    def _create_slider_widget(self, obj_data) -> HaspSliderItem:
        widget = HaspSliderItem(
            obj_data=obj_data,
            parent_widget=self
        )
        widget.valueChanged.connect(lambda obj_id, val: print(f"Slider {obj_id} changed to {val}"))
        return widget

    def _create_label_widget(self, obj_data: Dict) -> HaspLabelItem:
        return HaspLabelItem(
            obj_data=obj_data,
            parent_widget=self
        )

    def _create_img_widget(self, obj_data: Dict) -> HaspImageItem:
        return HaspImageItem(
            obj_data=obj_data,
            parent_widget=self
        )
