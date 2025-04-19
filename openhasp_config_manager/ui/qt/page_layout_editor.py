from typing import List

from PyQt6.QtCore import QSize, Qt, QRect
from PyQt6.QtGui import QPainter, QBrush, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from orjson import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.util import clear_layout


class OpenHaspPage:
    def __init__(self, device: Device, name: str, jsonl_components: List[JsonlComponent]):
        self.device = device
        self.name = name
        self.jsonl_components = jsonl_components


class PageLayoutEditorWidget(QWidget):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.device_processor = None
        self.create_layout()

    def create_layout(self):
        self.layout = QVBoxLayout(self)

    def clear_layout(self):
        clear_layout(self.layout)

    def set_page(self, page: OpenHaspPage or None):
        self.page = page
        self.clear_layout()
        if page is None:
            return
        self.device_processor = self.config_manager.create_device_processor(page.device)
        page_objects = self.get_page_objects(page)
        self.page_preview_widget = PagePreviewWidget(page, page_objects)
        self.layout.addWidget(self.page_preview_widget)
        self.page_preview_widget.set_objects(page_objects)

    def get_page_objects(self, page) -> List[dict]:
        if self.page is None:
            return []

        result = []
        for jsonl_component in self.page.jsonl_components:
            output_content = self.device_processor.normalize(self.page.device, jsonl_component)
            objects_in_jsonl = output_content.splitlines()
            loaded_objects = list(map(orjson.loads, objects_in_jsonl))
            result = result + loaded_objects

        return result


class PagePreviewWidget(QWidget):

    def __init__(self, page: OpenHaspPage, page_objects: List[dict], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.objects: List[dict] = page_objects

        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.MinimumExpanding
        )

    @property
    def page_width(self) -> int:
        return self.page.device.config.openhasp_config_manager.device.screen.width

    @property
    def page_height(self) -> int:
        return self.page.device.config.openhasp_config_manager.device.screen.height

    def sizeHint(self):
        return QSize(
            self.page_width,
            self.page_height,
        )

    def set_objects(self, loaded_objects: List[dict]):
        self.objects = loaded_objects
        self._trigger_refresh()

    def paintEvent(self, e):
        painter = QPainter(self)

        brush = QBrush()
        brush.setColor(QColor('black'))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        rect = QRect(0, 0, painter.device().width(), painter.device().height())
        painter.fillRect(rect, brush)

        padding = 0

        # Define our canvas.
        d_height = painter.device().height() - (padding * 2)
        d_width = painter.device().width() - (padding * 2)

        # Draw the objects
        for i, obj in enumerate(self.objects):
            object_type = obj.get("obj", "unknown")
            if object_type == "btn":
                self._draw_button(painter, obj, padding, d_width, d_height)
            elif object_type == "label":
                self._draw_label(painter, obj, padding, d_width, d_height)
            elif object_type == "slider":
                self._draw_slider(painter, obj, padding, d_width, d_height)
            elif object_type == "switch":
                self._draw_switch(painter, obj, padding, d_width, d_height)
            elif object_type == "img":
                self._draw_image(painter, obj, padding, d_width, d_height)
            elif object_type == "bar":
                self._draw_bar(painter, obj, padding, d_width, d_height)
            else:  # Handle unknown object types
                print(f"Unknown object type: {object_type}")

        painter.end()

    def _trigger_refresh(self):
        self.update()

    def _draw_label(self, painter, obj, padding, d_width, d_height):
        """
        Draws a label on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "red")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # Draw the text
        # painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj["text"])

    def _draw_button(self, painter, obj, padding, d_width, d_height):
        """
        Draws a button on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "blue")

        brush = QBrush()
        brush.setColor(QColor(object_bg_color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # Draw the text
        # painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj["text"])

    def _draw_slider(self, painter, obj, padding, d_width, d_height):
        """
        Draws a slider on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "gray")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # slider_min = obj.get("min", 0)
        # slider_max = obj.get("max", 100)
        # slider_value = obj.get("value", 50)
        #
        # # Draw the slider value
        # value_rect = QRect(
        #     padding,
        #     padding + d_height - height - (obj["y"] * d_height),
        #     (slider_value - slider_min) / (slider_max - slider_min) * width * d_width,
        #     height * d_height
        # )
        # painter.fillRect(value_rect, QColor('yellow'))

    def _draw_switch(self, painter, obj, padding, d_width, d_height):
        """
        Draws a switch on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "green")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # Draw the text
        # painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj["text"])

    def _draw_image(self, painter, obj, padding, d_width, d_height):
        """
        Draws an image on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "yellow")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # Draw the text
        # painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj["text"])

    def _draw_bar(self, painter, obj, padding, d_width, d_height):
        """
        Draws a bar on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return:
        """
        object_bg_color = obj.get("bg_color", "purple")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(painter, x, y, width, height, padding, d_width, d_height, color=object_bg_color)

        # Draw the text
        # painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj["text"])

    def _draw_scaled_square(self, painter, x, y, width, height, padding, d_width, d_height, color):
        """
        Draws a scaled square on the canvas.
        :param painter:
        :param width:
        :param height:
        :param padding:
        :param d_width:
        :param d_height:
        :param color:
        :return:
        """
        scaled_x = int((x / self.page_width) * d_width)
        scaled_y = int((y / self.page_height) * d_height)
        scaled_width = int((width / self.page_width) * d_width)
        scaled_height = int((height / self.page_height) * d_height)

        rect = QRect(
            padding + scaled_x,
            padding + scaled_y,
            scaled_width,
            scaled_height
        )
        brush = QBrush()
        brush.setColor(QColor(color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        painter.fillRect(rect, brush)
