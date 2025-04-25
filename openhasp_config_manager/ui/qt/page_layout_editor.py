from collections import OrderedDict
from typing import List, Tuple, Dict, Set

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtCore import QSize, Qt, QRect, QRectF
from PyQt6.QtGui import QPainter, QBrush, QColor, QMouseEvent, QPainterPath, QFont, QPen
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QPushButton, QHBoxLayout, QTextEdit
from orjson import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.component import JsonlComponent
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import IntegratedIcon
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
        self.jsonl_component_objects: OrderedDict[str, List[Dict]] = OrderedDict()

        self.device_pages_data = None
        self.current_index = 1

        self.create_layout()

    def create_layout(self):
        self.layout = QVBoxLayout(self)

        self.page_selector = self._create_page_selector()
        self.layout.addWidget(self.page_selector)

        self.preview_container = QWidget()
        self.preview_container.setLayout(QVBoxLayout())
        self.layout.addWidget(self.preview_container)

    def _on_previous_page_clicked(self):
        self.previous_page_index()

    def _on_next_page_clicked(self):
        self.next_page_index()

    def clear(self):
        clear_layout(self.preview_container.layout())
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
        self.preview_container.layout().addWidget(self.page_preview_widget)

        self.page_jsonl_preview = PageJsonlPreviewWidget(device_pages_data)
        self.preview_container.layout().addWidget(self.page_jsonl_preview)

        self.set_page_index(index=1)

    def set_page_index(self, index: int):
        print("Setting page index", index)
        self.current_index = index
        self.page_objects = self.get_page_objects(index=index)
        print(f"Page objects: {self.page_objects}")
        self.page_preview_widget.set_objects(self.page_objects)

        self.page_jsonl_preview.set_objects(self.page_objects)

    def next_page_index(self):
        """
        Cycle to the next available page index, skipping page 0 and rolling over to the first page.
        """
        usable_page_indices = self.get_used_page_indices() - {0}
        usable_page_indices = list(sorted(usable_page_indices))
        current_page_index_position_in_set = usable_page_indices.index(self.current_index)
        new_page_index_position_in_set = (current_page_index_position_in_set + 1) % len(usable_page_indices)
        self.set_page_index(usable_page_indices[new_page_index_position_in_set])

    def previous_page_index(self):
        """
        Cycle to the previous available page index, skipping page 0 and rolling over to the last page.
        """
        usable_page_indices = self.get_used_page_indices() - {0}
        usable_page_indices = list(sorted(usable_page_indices))
        current_page_index_position_in_set = usable_page_indices.index(self.current_index)
        new_page_index_position_in_set = (current_page_index_position_in_set - 1) % len(usable_page_indices)
        self.set_page_index(usable_page_indices[new_page_index_position_in_set])

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

    def _create_page_selector(self) -> QWidget:
        page_selector_widget = QWidget()
        page_selector_widget.setLayout(QHBoxLayout())

        self._previous_page_button_widget = QPushButton("Previous Page")
        self._previous_page_button_widget.clicked.connect(self._on_previous_page_clicked)
        page_selector_widget.layout().addWidget(self._previous_page_button_widget)

        self._next_page_button_widget = QPushButton("Next Page")
        self._next_page_button_widget.clicked.connect(self._on_next_page_clicked)
        page_selector_widget.layout().addWidget(self._next_page_button_widget)

        return page_selector_widget


class PageJsonlPreviewWidget(QTextEdit):
    def __init__(self, page: OpenHaspDevicePagesData, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Roboto Mono", 10))

        self.set_page(page)

    def set_page(self, page: OpenHaspDevicePagesData):
        self.page = page
        self.setText(page.jsonl_components[0].content)

    def set_objects(self, page_objects: List[dict]):
        """
        Set the objects for the page.
        :param page_objects: the list of objects to set
        """
        sorted_page_objects = sorted(page_objects, key=lambda obj: (
        obj.get("page", 0), obj.get("id", 0), obj.get("y", ""), obj.get("x", "")))

        content = "\n".join(map(lambda x: orjson.dumps(x).decode(), sorted_page_objects))
        self.setText(content)


class PagePreviewWidget(QWidget):
    clickedValue = QtCore.pyqtSignal(int)

    def __init__(self, page: OpenHaspDevicePagesData, page_objects: List[dict], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.objects: List[dict] = page_objects

        self._padding = 0

        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

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

    def heightForWidth(self, width):
        # ratio = self.page_width / self.page_height
        return int((width / self.page_width) * self.page_height)

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
        object_id = obj.get("id", None)
        print(f"Drawing label with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)

        text = obj.get("text", "")
        text_color = obj.get("text_color", None)
        text_font = obj.get("text_font", 25)
        text_align = obj.get("align", "left")
        object_bg_color = obj.get("bg_color", None)
        border_width = obj.get("border_width", 0)
        border_color = obj.get("border_color", None)

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color,
            border_width=border_width, border_color=border_color,
        )

        text_alignment_flag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if text_align == "center":
            text_alignment_flag = Qt.AlignmentFlag.AlignCenter
        elif text_align == "right":
            text_alignment_flag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=text, text_color=text_color, pixel_size=text_font,
            flags=text_alignment_flag,
            border_width=border_width, border_color=border_color,
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
        object_id = obj.get("id", None)
        print(f"Drawing button with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        object_bg_color = obj.get("bg_color", "blue")
        text = obj.get("text", "")
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)
        radius = obj.get("radius", 0)
        action = obj.get("action", None)

        brush = QBrush()
        brush.setColor(QColor(object_bg_color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color, corner_radius=radius,
        )

        self._draw_scaled_text(
            painter, x, y, width, height, padding, d_width, d_height,
            text=text, text_color=text_color, pixel_size=text_font
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
        object_id = obj.get("id", None)
        print(f"Drawing slider with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        object_bg_color = obj.get("bg_color", "gray")
        knob_color = obj.get("bg_color20", "lightgray")
        radius = obj.get("radius", 0)
        knob_radius = obj.get("radius20", 0)
        slider_min = obj.get("min", 0)
        slider_max = obj.get("max", 100)
        slider_value = obj.get("value", 0)

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color, corner_radius=radius,
        )

        # Draw the slider value
        self._draw_scaled_circle(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=knob_color, radius=knob_radius,
        )

    def _draw_switch(self, painter, obj, padding, d_width, d_height):
        """
        Draws a switch on the canvas.
        :param painter: the painter to use for drawing
        :param obj: the object to draw
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        """
        object_id = obj.get("id", None)
        print(f"Drawing switch with id {object_id}: {obj}")

        value = obj.get("val", 0)
        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        corner_radius = obj.get("radius00", 0)
        object_bg_color = obj.get("bg_color", "green")
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color, corner_radius=corner_radius,
        )

        # Draw the knob
        knob_radius = obj.get("radius20", 0)
        knob_color = obj.get("bg_color20", "lightgray")

        knob_x = x + (width - 1) if value else x
        self._draw_scaled_circle(
            painter, knob_x, y, width, height, padding, d_width, d_height,
            fill_color=knob_color, radius=knob_radius
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
        object_id = obj.get("id", None)
        print(f"Drawing image with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        object_bg_color = obj.get("bg_color", "yellow")

        self._draw_scaled_rect(
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
        object_id = obj.get("id", None)
        print(f"Drawing bar with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        corner_radius = obj.get("radius", None)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)
        object_bg_color = obj.get("bg_color", "purple")

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color, corner_radius=corner_radius
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
        object_id = obj.get("id", None)
        print(f"Drawing messagebox with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        text_font = obj.get("text_font", 25)
        text_color = obj.get("text_color", None)
        object_bg_color = obj.get("bg_color", "orange")

        self._draw_scaled_rect(
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
        object_id = obj.get("id", None)
        print(f"Drawing object with id {object_id}: {obj}")

        x = obj.get("x", 0)
        y = obj.get("y", 0)
        width = obj.get("w", 50)
        height = obj.get("h", 50)
        object_bg_color = obj.get("bg_color", "gray")

        self._draw_scaled_rect(
            painter, x, y, width, height, padding, d_width, d_height,
            fill_color=object_bg_color
        )

    def _draw_scaled_rect(
        self,
        painter, x, y, width, height, padding, d_width, d_height,
        fill_color: str, corner_radius: int = 0,
        border_width: int = 0, border_color: str = "#FFFFFF"
    ):
        """
        Helper method to draw a scaled rectangle on the canvas.
        :param painter: the painter to use for drawing
        :param x: the x position of the rectangle
        :param y: the y position of the rectangle
        :param width: the width of the rectangle
        :param height: the height of the rectangle
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :param fill_color: the fill color of the rectangle
        :param corner_radius: the corner radius of the rectangle
        :param border_width: the border width of the rectangle
        :param border_color: the border color of the rectangle
        """
        if fill_color is None:
            return
        if border_color is None:
            border_color = "#FFFFFF"
        if corner_radius is None:
            corner_radius = 0

        scaled_x, scaled_y, scaled_width, scaled_height = self.__get_scaled_rect(
            x, y, width, height, padding, d_width, d_height
        )

        scale_factor = 0.8 * (d_height / self.page_height)
        scaled_corner_radius = min(scaled_height / 2, int(corner_radius * scale_factor))

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
        path.addRoundedRect(rect, scaled_corner_radius, scaled_corner_radius)
        painter.fillPath(path, brush)

        # draw border
        if border_width > 0:
            scaled_border_width = int(border_width * scale_factor)
            border_pen = QPen(QColor(border_color))
            border_pen.setWidth(scaled_border_width)
            path = QPainterPath()

            # inset rect to account for border width
            border_rect = QRectF(
                padding + scaled_x + scaled_border_width,
                padding + scaled_y + scaled_border_width,
                scaled_width - (scaled_border_width * 2),
                scaled_height - (scaled_border_width * 2)
            )
            path.addRoundedRect(border_rect, scaled_corner_radius, scaled_corner_radius)
            painter.strokePath(path, border_pen)

    def _draw_scaled_circle(self, painter, x, y, width, height, padding, d_width, d_height, fill_color, radius):
        """
        Helper method to draw a scaled circle on the canvas.
        :param painter: the painter to use for drawing
        :param x: the x position of the circle
        :param y: the y position of the circle
        :param width: the width of the circle
        :param height: the height of the circle
        :param padding: the padding around the canvas
        :param d_width: the width of the canvas
        :param d_height: the height of the canvas
        :param fill_color: the fill color of the circle
        :param radius: the radius of the circle
        """
        if fill_color is None:
            return

        if radius <= 0:
            return

        scaled_x, scaled_y, scaled_width, scaled_height = self.__get_scaled_rect(
            x, y, width, height, padding, d_width, d_height
        )

        scale_factor = 0.8 * (d_height / self.page_height)
        scaled_radius = int(radius * scale_factor)
        scaled_radius = min(scaled_radius, scaled_height // 2)

        rect = QRectF(
            padding + scaled_x,
            padding + scaled_y,
            scaled_radius * 2,
            scaled_radius * 2
        )
        brush = QBrush(QColor(fill_color))
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(rect)
        painter.fillPath(path, brush)

    def _draw_scaled_text(
        self, painter, x, y, width, height, padding, d_width, d_height, text: str = "",
        text_color: str = "white", pixel_size: int = 48, flags: int = Qt.AlignmentFlag.AlignCenter,
        border_width: int = 0, border_color: str = None
    ):
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
        :param pixel_size: the pixel size of the text
        :param flags: the text alignment flags
        :param border_width: the border width of the text
        :param border_color: the border color of the text
        """
        if not text:
            return
        if text_color is None:
            text_color = "white"

        scaled_x, scaled_y, scaled_width, scaled_height = self.__get_scaled_rect(
            x, y, width, height, padding, d_width, d_height
        )

        scale_factor = 0.7 * (d_height / self.page_height)
        scaled_pixel_size = int(pixel_size * scale_factor)

        # draw border first
        if border_width > 0:
            scaled_border_width = int(border_width * scale_factor)
            border_pen = QPen(QColor(border_color))
            border_pen.setWidth(scaled_border_width)
            path = QPainterPath()

            # inset rect to account for border width
            border_rect = QRectF(
                padding + scaled_x + scaled_border_width,
                padding + scaled_y + scaled_border_width,
                scaled_width - (scaled_border_width * 2),
                scaled_height - (scaled_border_width * 2)
            )

            path.addRect(border_rect)
            painter.strokePath(path, border_pen)

        # replace unicode chars with icons from material design icons
        text = self._replace_unicode_with_icons(text)

        rect = QRectF(
            padding + scaled_x,
            padding + scaled_y,
            scaled_width,
            scaled_height
        )
        painter.setPen(QColor(text_color))
        font = QFont("Roboto Condensed", scaled_pixel_size, QFont.Weight.Normal)
        # print(font.family())
        # print(font.exactMatch())
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

    def _replace_unicode_with_icons(self, text: str) -> str:
        """
        Replaces unicode characters in the text with icons from material design icons.
        :param text: the text to process
        :return: the text with unicode characters replaced with icons
        """
        for unicode_char, icon_name in IntegratedIcon.entries():
            icon_charmap = qta.charmap(f"mdi6.{icon_name}")
            text = text.replace(unicode_char, icon_charmap)

        return text
