from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush, QImage

from openhasp_config_manager.gui.domain.preview_images import decode_binary_image
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


def load_image(path: Path) -> Optional[QImage]:
    """:return: the image of a PNG or a binary image file (`.bin`), None if it can't be read"""
    if path.suffix == ".bin":
        decoded = decode_binary_image(path.read_bytes())
        if decoded is None:
            return None
        width, height, rgba = decoded
        # the QImage only references the bytes
        return QImage(rgba, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
    image = QImage(str(path))
    return None if image.isNull() else image


class HaspImageItem(EditableWidget):
    clicked = QtCore.pyqtSignal(int)

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

        self.setPos(self.obj_x, self.obj_y)

        self.image: Optional[QImage] = None
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
    def outline_width(self) -> float:
        return max(number(self.style("outline_width", 0), 0), 0)

    @property
    def outline_pad(self) -> float:
        return max(number(self.style("outline_pad", 0), 0), 0)

    def boundingRect(self):
        # the outline is drawn outside of the object
        reach = self.outline_width + self.outline_pad if self.outline_width > 0 else 0
        return super().boundingRect().adjusted(-reach, -reach, reach, reach)

    def _paint_outline(self, painter):
        """Like LVGL: a ring around the object, `outline_pad` away from it, with the corners rounded further out."""
        width, pad = self.outline_width, self.outline_pad
        if width <= 0:
            return
        color = to_color(self.style("outline_color"), "#000000")
        color.setAlphaF(max(0.0, min(number(self.style("outline_opa", 255), 255) / 255, 1.0)))
        # a pen is centered on the line it draws
        offset = pad + width / 2
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(color, width))
        painter.drawRoundedRect(
            self.obj_rect.adjusted(-offset, -offset, offset, offset), self.radius + offset, self.radius + offset
        )

    def paint(self, painter, option, widget=None):
        local_rect = self.obj_rect

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        if self.image is not None:
            # like the plate: the image in its size, cut off by the object
            painter.save()
            painter.setClipRect(local_rect)
            painter.scale(self.zoom, self.zoom)
            painter.drawImage(0, 0, self.image)
            painter.restore()
        else:
            # no image the preview knows: a placeholder
            bg_color = self.bg_color
            painter.setBrush(QBrush(QColor(bg_color)))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(local_rect, self.radius, self.radius)

            painter.setPen(QtGui.QPen(QColor("black"), 1))
            painter.drawText(local_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "IMG")

        self._paint_outline(painter)

        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)
