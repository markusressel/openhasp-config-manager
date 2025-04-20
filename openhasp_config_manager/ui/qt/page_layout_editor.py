from typing import List, Tuple, Dict, Set

from PyQt6 import QtCore
from PyQt6.QtCore import QSize, Qt, QRect, QRectF
from PyQt6.QtGui import QPainter, QBrush, QColor, QMouseEvent, QPainterPath
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from orjson import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.util import clear_layout


class OpenHaspDevicePagesData:
    def __init__(self, device: Device, name: str, jsonl_components: List[JsonlComponent]):
        self.device = device
        self.name = name
        self.jsonl_components = jsonl_components


class PageLayoutEditorWidget(QWidget):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.device_processor = None
        # map of <json component name, list of objects>
        self.jsonl_component_objects: Dict[str, List[Dict]] = {}
        self.create_layout()

    def create_layout(self):
        self.layout = QVBoxLayout(self)

    def clear(self):
        clear_layout(self.layout)
        self.current_index = 1
        self.jsonl_component_objects.clear()

    def set_data(self, device_pages_data: OpenHaspDevicePagesData or None):
        self.device_pages_data = device_pages_data
        self.clear()
        if device_pages_data is None:
            return
        self.device_processor = self.config_manager.create_device_processor(device_pages_data.device)

        # load jsonl component objects
        for jsonl_component in self.device_pages_data.jsonl_components:
            normalized_jsonl_component = self.device_processor.normalize(self.device_pages_data.device, jsonl_component)
            objects_in_jsonl = normalized_jsonl_component.splitlines()
            loaded_objects = list(map(orjson.loads, objects_in_jsonl))
            self.jsonl_component_objects[jsonl_component.name] = loaded_objects

        self.page_preview_widget = PagePreviewWidget(device_pages_data, [])
        self.page_preview_widget.clickedValue.connect(self.on_clicked_value)
        self.layout.addWidget(self.page_preview_widget)

        self.set_page_index(index=1)

    def on_clicked_value(self):
        self.next_page_index()

    def set_page_index(self, index: int):
        print("Setting page index", index)
        self.current_index = index
        self.page_objects = self.get_page_objects(index=index)
        print(f"Page objects: {self.page_objects}")
        self.page_preview_widget.set_objects(self.page_objects)

    def get_used_page_indices(self) -> Set[int]:
        """
        Get the used page indices from the jsonl component objects.
        :return: a list of used page indices
        """
        if self.device_pages_data is None:
            return set()

        used_page_indices = set()
        for jsonl_component_name, objects_in_jsonl in self.jsonl_component_objects.items():
            for obj in objects_in_jsonl:
                object_page_index = obj.get("page", None)
                if object_page_index is not None:
                    used_page_indices.add(object_page_index)

        print(f"Used page indices: {used_page_indices}")

        return used_page_indices

    def get_page_objects(self, index: int, include_global: bool = True) -> List[dict]:
        """
        Get the page objects for the given page index.
        :param index: the index of the page
        :return: a list of objects for the page
        """
        if self.device_pages_data is None:
            return []

        result = []
        for jsonl_component_name, objects_in_jsonl in self.jsonl_component_objects.items():
            result = result + objects_in_jsonl

        # Filter the objects based on the index
        result = [
            obj for obj in result if
            obj.get("page") == index or (obj.get("page") == 0 if include_global else False)
        ]

        # Filter hidden objects
        result = [obj for obj in result if not obj.get("hidden", False)]

        # Draw objects on page 0 last (on top)
        result.sort(key=lambda obj: obj.get("page") == 0)

        return result

    def next_page_index(self):
        usable_page_indices = self.get_used_page_indices() - {0}
        usable_page_indices = list(sorted(usable_page_indices))
        current_page_index_position_in_set = usable_page_indices.index(self.current_index)
        new_page_index_position_in_set = (current_page_index_position_in_set + 1) % len(usable_page_indices)
        self.set_page_index(usable_page_indices[new_page_index_position_in_set])


class PagePreviewWidget(QWidget):
    clickedValue = QtCore.pyqtSignal(int)

    def __init__(self, page: OpenHaspDevicePagesData, page_objects: List[dict], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.objects: List[dict] = page_objects

        self._padding = 0

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

    def _calculate_clicked_value(self, e: QMouseEvent):
        parent = self.parent()
        vmin, vmax = parent.minimumHeight(), parent.maximumHeight()
        d_height = self.size().height() + (self._padding * 2)
        click_y = e.pos().y() - self._padding

        pc = (d_height - click_y) / d_height
        value = vmin + pc * (vmax - vmin)
        self.clickedValue.emit(value)

    def mouseMoveEvent(self, e: QMouseEvent):
        pass
        # self._calculate_clicked_value(e)

    def mousePressEvent(self, e: QMouseEvent):
        self._calculate_clicked_value(e)

    def paintEvent(self, e):
        painter = QPainter(self)

        brush = QBrush()
        brush.setColor(QColor('black'))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        rect = QRect(0, 0, painter.device().width(), painter.device().height())
        painter.eraseRect(rect)
        painter.fillRect(rect, brush)

        padding = 0

        # Define our canvas.
        d_height = painter.device().height() - (padding * 2)
        d_width = painter.device().width() - (padding * 2)

        # Draw the objects
        for i, obj in enumerate(self.objects):
            object_type = obj.get("obj", None)
            if object_type is None:
                continue
            elif object_type == "btn":
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
            elif object_type == "msgbox":
                self._draw_messagebox(painter, obj, padding, d_width, d_height)
            elif object_type == "obj":
                self._draw_obj(painter, obj, padding, d_width, d_height)
            else:
                print(f"Unknown object type: {object_type}")

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
        """
        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        text = obj.get("text", "")
        text_color = obj.get("text_color", None)
        text_font = obj.get("text_font", 25)
        text_align = obj.get("align", "left")
        object_bg_color = obj.get("bg_color", None)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

        text_alignment_flag = Qt.AlignmentFlag.AlignLeft
        if text_align == "center":
            text_alignment_flag = Qt.AlignmentFlag.AlignCenter
        elif text_align == "right":
            text_alignment_flag = Qt.AlignmentFlag.AlignRight
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=text, text_color=text_color, pixel_size=text_font,
            flags=text_alignment_flag
        )

    def _draw_button(self, painter, obj, padding, d_width, d_height):
        """
        Draws a button on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "blue")

        brush = QBrush()
        brush.setColor(QColor(object_bg_color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)
        radius = obj.get("radius", 0)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color, corner_radius=radius,
        )

        # Draw the text
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=obj.get("text", ""), text_color=text_color, pixel_size=text_font
        )

    def _draw_slider(self, painter, obj, padding, d_width, d_height):
        """
        Draws a slider on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "gray")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

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
        """
        object_bg_color = obj.get("bg_color", "green")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

        # Draw the text
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=obj.get("text", ""), text_color=text_color, pixel_size=text_font
        )

    def _draw_image(self, painter, obj, padding, d_width, d_height):
        """
        Draws an image on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "yellow")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

    def _draw_bar(self, painter, obj, padding, d_width, d_height):
        """
        Draws a bar on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "purple")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

        # Draw the text
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=obj.get("text", ""), text_color=text_color, pixel_size=text_font
        )

    def _draw_messagebox(self, painter, obj, padding, d_width, d_height):
        """
        Draws a messagebox on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "orange")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

        # Draw the text
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=obj.get("text", ""), text_color=text_color, pixel_size=text_font
        )

    def _draw_obj(self, painter, obj, padding, d_width, d_height):
        """
        Draws a generic object on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_bg_color = obj.get("bg_color", "gray")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        self._draw_scaled_square(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

    def _draw_scaled_square(
        self,
        painter, x, y, width, height, padding, d_width, d_height,
        fill_color, corner_radius: int = 0,
    ):
        """
        Helper method to draw a scaled square on the canvas.
        :param painter: the painter to use for drawing
        :param x: the x position of the square
        :param y: the y position of the square
        :param width: the width of the square
        :param height: the height of the square
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :param fill_color: the fill color of the square
        :param corner_radius: the corner radius of the square
        """
        if fill_color is None:
            return

        scaled_x, scaled_y, scaled_width, scaled_height = self.__get_scaled_rect(
            x, y, width, height, padding, d_width, d_height
        )

        rect = QRectF(
            padding + scaled_x,
            padding + scaled_y,
            scaled_width,
            scaled_height
        )
        brush = QBrush(QColor(fill_color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        painter.setBrush(brush)

        # Add the rect to path.
        path.addRoundedRect(rect, corner_radius, corner_radius)
        painter.setClipPath(path)

        # Fill shape, draw the border and center the text.
        painter.fillPath(path, brush)

        # painter.fillRect(rect, brush)

    def _draw_scaled_text(self, painter, x, y, width, height, padding, d_width, d_height, text: str = "",
                          text_color: str = "white", pixel_size: int = 48, flags: int = Qt.AlignmentFlag.AlignCenter):
        """
        Helper method to draw scaled text on the canvas.
        :param painter: the painter to use for drawing
        :param x: the x position of the text
        :param y: the y position of the text
        :param width: the width of the text
        :param height: the height of the text
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :param text: the text to draw
        :param text_color: the color of the text
        """
        if text_color is None:
            text_color = "white"

        scaled_x, scaled_y, scaled_width, scaled_height = self.__get_scaled_rect(
            x, y, width, height, padding, d_width, d_height
        )

        scale_factor = d_width / self.page_width
        scaled_pixel_size = int(pixel_size * scale_factor)

        rect = QRect(
            padding + scaled_x,
            padding + scaled_y,
            scaled_width,
            scaled_height
        )
        painter.setPen(QColor(text_color))
        font = painter.font()
        font.setPixelSize(scaled_pixel_size)
        painter.setFont(font)
        painter.drawText(rect, flags, text)

    def __get_scaled_rect(self, x, y, width, height, padding, d_width, d_height) -> Tuple[int, int, int, int]:
        """
        Helper method to get the scaled rectangle for the given parameters.
        :param x: the x position of the rectangle
        :param y: the y position of the rectangle
        :param width: the width of the rectangle
        :param height: the height of the rectangle
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :return: a tuple of (x, y, width, height) for the scaled rectangle
        """
        scaled_x = int((x / self.page_width) * d_width)
        scaled_y = int((y / self.page_height) * d_height)
        scaled_width = int((width / self.page_width) * d_width)
        scaled_height = int((height / self.page_height) * d_height)

        return scaled_x, scaled_y, scaled_width, scaled_height
