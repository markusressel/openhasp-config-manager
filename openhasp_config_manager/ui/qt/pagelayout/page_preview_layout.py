import logging
from copy import deepcopy
from typing import List, Tuple

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtCore import QSize, Qt, QRect, QRectF
from PyQt6.QtGui import QPainter, QBrush, QColor, QMouseEvent, QPainterPath, QFont, QPen
from PyQt6.QtWidgets import QWidget, QSizePolicy, QGraphicsView, QGraphicsScene

from openhasp_config_manager.openhasp_client.icons import IntegratedIcon
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.bar import HaspBarItem
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.button import HaspButtonItem
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.image import HaspImageItem
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.label import HaspLabelItem
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.slider import HaspSliderItem
from openhasp_config_manager.ui.qt.pagelayout.openhasp_widgets.switch import HaspSwitchItem
from openhasp_config_manager.ui.qt.pagelayout.page_layout_editor import OpenHaspDevicePagesData


class PagePreviewWidget2(QGraphicsView):
    clickedValue = QtCore.pyqtSignal(int)
    buttonClicked = QtCore.pyqtSignal(dict)

    @property
    def page_width(self) -> int:
        return self.page.device.config.openhasp_config_manager.device.screen.width

    @property
    def page_height(self) -> int:
        return self.page.device.config.openhasp_config_manager.device.screen.height

    def __init__(self, page: OpenHaspDevicePagesData, page_objects: List[dict], *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.page = page

        # 1. Setup the Scene (use the device's actual native resolution)
        self.native_width = self.page_width
        self.native_height = self.page_height

        self.scene = QGraphicsScene(0, 0, self.native_width, self.native_height)
        self.scene.setBackgroundBrush(QColor('black'))
        self.setScene(self.scene)

        # 2. Make it scale smoothly
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.objects: List[dict] = page_objects
        self.load_objects()

    def load_objects(self):
        self.scene.clear()
        for obj in self.objects:
            obj_type = obj.get("obj")
            if not obj_type:
                continue  # Skip objects with no type

            if obj_type == "btn":
                logging.debug(f"Adding button item: {obj}")
                item = HaspButtonItem(obj)
                # item.clicked.connect(self.clickedValue.emit)
                this_object = deepcopy(obj)
                item.clicked.connect(lambda obj_id: self.buttonClicked.emit(this_object))
                self.scene.addItem(item)
            elif obj_type == "switch":
                logging.debug(f"Adding switch item: {obj}")
                item = HaspSwitchItem(obj)
                item.toggled.connect(lambda obj_id, val: print(f"Switch {obj_id} toggled to {val}"))
                self.scene.addItem(item)
            elif obj_type == "bar":
                logging.debug(f"Adding bar item: {obj}")
                item = HaspBarItem(obj)
                self.scene.addItem(item)
            elif obj_type == "slider":
                logging.debug(f"Adding slider item: {obj}")
                item = HaspSliderItem(obj)
                item.valueChanged.connect(lambda obj_id, val: print(f"Slider {obj_id} changed to {val}"))
                self.scene.addItem(item)
            elif obj_type == "label":
                logging.debug(f"Adding label item: {obj}")
                item = HaspLabelItem(obj)
                self.scene.addItem(item)
            elif obj_type == "img":
                logging.debug(f"Adding image item: {obj}")
                item = HaspImageItem(obj)
                self.scene.addItem(item)

    def set_objects(self, loaded_objects: List[dict]):
        self.objects = loaded_objects
        self.load_objects()
        self._trigger_refresh()

    def _trigger_refresh(self):
        self.update()

    def resizeEvent(self, event):
        # This keeps the aspect ratio and fits the scene into the view
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        super().resizeEvent(event)


class PagePreviewWidget(QWidget):
    """
    Draws a preview of a page layout.
    """
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
        corner_radius = obj.get("radius", height)
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
