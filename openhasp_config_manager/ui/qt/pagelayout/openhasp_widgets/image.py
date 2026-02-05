from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import QColor, QBrush, QPixmap
from PyQt6.QtWidgets import QGraphicsObject


class HaspImageItem(QGraphicsObject):
    clicked = QtCore.pyqtSignal(int)

    def __init__(self, obj_data, parent_widget=None):
        super().__init__()
        self.obj_data = obj_data
        self.parent_widget = parent_widget
        self.obj_id = obj_data.get("id", 0)

        # Dimensions from JSON
        self.w = obj_data.get("w", 50)
        self.h = obj_data.get("h", 50)
        self.setPos(obj_data.get("x", 0), obj_data.get("y", 0))

        # Check for actual image source (e.g., 'src': 'L:/path/to/img.png')
        self.pixmap = None
        src = obj_data.get("src")
        if src:
            self._load_pixmap(src)

    def _load_pixmap(self, src):
        """Attempts to load a pixmap from the source string."""
        # Strip LVGL drive prefixes (e.g., 'L:', 'S:') if they exist
        clean_path = src.split(":")[-1] if ":" in src else src
        # You might need to join this with your config_dir path
        self.pixmap = QPixmap(clean_path)
        if not self.pixmap.isNull():
            # Scale to fit while maintaining aspect ratio or force fill
            self.pixmap = self.pixmap.scaled(
                self.w, self.h,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, painter, option, widget=None):
        if not painter:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        if self.pixmap and not self.pixmap.isNull():
            # Draw the actual image
            painter.drawPixmap(0, 0, self.pixmap)
        else:
            # Fallback to your original logic: Yellow placeholder
            bg_color = self.obj_data.get("bg_color", "yellow")
            painter.setBrush(QBrush(QColor(bg_color)))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRect(self.boundingRect())

            # Optional: Draw a subtle "X" or icon to indicate missing image
            painter.setPen(QtGui.QPen(QColor("black"), 1))
            painter.drawText(self.boundingRect(), QtCore.Qt.AlignmentFlag.AlignCenter, "IMG")

    def mousePressEvent(self, event):
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)