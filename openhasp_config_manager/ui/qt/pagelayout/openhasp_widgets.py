from PyQt6 import QtCore
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem


class HaspButtonItem(QGraphicsRectItem):
    clicked = QtCore.pyqtSignal(int)

    def __init__(self, obj_data):
        # Initialize with native coordinates
        super().__init__(
            obj_data.get("x", 0),
            obj_data.get("y", 0),
            obj_data.get("w", 50),
            obj_data.get("h", 50)
        )
        self.obj_id = obj_data.get("id", 0)
        self.setBrush(QColor(obj_data.get("bg_color", "blue")))

        # Add text as a child item so it moves with the button
        text = QGraphicsTextItem(obj_data.get("text", ""), self)
        text.setDefaultTextColor(QColor("white"))
        # Center text logic here...

    def mousePressEvent(self, event):
        # This only triggers if the user clicks INSIDE this specific item
        print(f"Object {self.obj_id} clicked!")
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)

