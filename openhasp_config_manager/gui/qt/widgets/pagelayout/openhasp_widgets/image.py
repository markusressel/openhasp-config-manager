import dataclasses
import math
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.preview_images import decode_binary_image
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, opacity, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


def load_image(path: Path) -> Optional[QtGui.QImage]:
    """:return: the image of a PNG or a binary image file (`.bin`), None if it can't be read"""
    if path.suffix == ".bin":
        decoded = decode_binary_image(path.read_bytes())
        if decoded is None:
            return None
        width, height, rgba = decoded
        # the QImage only references the bytes
        return QtGui.QImage(rgba, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888).copy()
    image = QtGui.QImage(str(path))
    return None if image.isNull() else image


class HaspImageItem(EditableWidget):
    @property
    def src(self) -> str:
        return self.obj_data.get("src", "")

    @property
    def bg_color(self) -> str:
        return self.obj_data.get("bg_color", "yellow")

    @property
    def zoom(self) -> float:
        """The scale of the image. The plate can't zoom binary images from flash."""
        zoom = self.obj_data.get("zoom", 256)
        if self.src.endswith(".bin") or not isinstance(zoom, (int, float)) or zoom <= 0:
            return 1.0
        return zoom / 256

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data, parent_widget)

        self.image: Optional[QtGui.QImage] = None
        self._load_image()

    def _load_image(self):
        """Reads the file of `src` from the config of the device. Images from a URL (see `push_image`) are not known."""
        self.image = None
        find_file = getattr(self.parent_widget, "image_file", None)
        path = find_file(self.src) if find_file is not None else None
        if path is not None and path.is_file():
            self.image = load_image(path)

    def _on_data_changed(self):
        self._load_image()

    @property
    def radius(self) -> float:
        return max(number(self.style("radius", 0), 0), 0)

    @property
    def angle(self) -> float:
        """The rotation in degrees (`angle` is in tenths of a degree)."""
        return number(self.obj_data.get("angle"), 0) / 10

    def _box(self):
        """The shadow and outline of the object: the plate draws no background or border for an image."""
        return dataclasses.replace(box_style(self), bg_opa=0, border_width=0)

    def boundingRect(self):
        # the shadow and the outline are drawn outside of the object, a zoomed or turned image reaches further
        box = self._box()
        reach = max(
            box.outline_width + box.outline_pad if box.outline_width > 0 else 0,
            box.shadow_width + max(box.shadow_spread, 0) + max(abs(box.shadow_ofs_x), abs(box.shadow_ofs_y)),
        )
        rect = super().boundingRect().adjusted(-reach, -reach, reach, reach)
        if self.image is not None and (self.zoom != 1.0 or self.angle):
            diagonal = math.hypot(self.image.width(), self.image.height()) * max(self.zoom, 1.0)
            rect = rect.united(QtCore.QRectF(self.obj_w / 2 - diagonal / 2, self.obj_h / 2 - diagonal / 2, diagonal, diagonal))
        return rect

    def paint(self, painter, option, widget=None):
        local_rect = self.obj_rect

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        draw_box(painter, local_rect, self._box())

        if self.image is not None:
            painter.save()
            transformed = self.zoom != 1.0 or self.angle
            if transformed:
                # like the plate: turned and scaled around the middle of the image, it may reach over the edge of the object
                painter.translate(self.image.width() / 2, self.image.height() / 2)
                painter.rotate(self.angle)
                painter.scale(self.zoom, self.zoom)
                painter.translate(-self.image.width() / 2, -self.image.height() / 2)
            else:
                # the image in its size, cut off by the object
                painter.setClipRect(local_rect)
            painter.setOpacity(painter.opacity() * opacity(self.style("image_opa", 255)))
            painter.drawImage(0, 0, self.image)
            recolor_opa = number(self.style("image_recolor_opa", 0), 0)
            if recolor_opa > 0:
                # the tint covers only what the image draws
                tint = to_color(self.style("image_recolor"), "#000000")
                tint.setAlphaF(opacity(recolor_opa))
                painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceAtop)
                painter.fillRect(QtCore.QRectF(0, 0, self.image.width(), self.image.height()), tint)
            painter.restore()
        else:
            # no image the preview knows: a placeholder
            bg_color = self.bg_color
            painter.setBrush(QtGui.QBrush(QtGui.QColor(bg_color)))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(local_rect, self.radius, self.radius)

            painter.setPen(QtGui.QPen(QtGui.QColor("black"), 1))
            painter.drawText(local_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "IMG")

        super().paint(painter, option, widget)
