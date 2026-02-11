from typing import Dict

from PyQt6 import QtGui, QtCore, QtWidgets
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem


class EditableWidget(QGraphicsObject):

    @property
    def obj_data(self):
        return self._object_data

    @property
    def obj_id(self):
        return self.obj_data.get("id", 0)

    @property
    def obj_x(self) -> int:
        return self.obj_data.get("x", 0)

    @property
    def obj_y(self) -> int:
        return self.obj_data.get("y", 0)

    @property
    def obj_w(self) -> int:
        return self.obj_data.get("w", 80)

    @property
    def obj_h(self) -> int:
        return self.obj_data.get("h", 40)

    def __init__(self, object_data: Dict, *args, **kwargs):
        self._object_data = object_data
        super().__init__(*args, **kwargs)

    @property
    def editable(self):
        return QGraphicsItem.GraphicsItemFlag.ItemIsSelectable in self.flags()

    @editable.setter
    def editable(self, value: bool):
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, value)

    @property
    def movable(self):
        return QGraphicsItem.GraphicsItemFlag.ItemIsMovable in self.flags()

    @movable.setter
    def movable(self, value: bool):
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, value)

    @property
    def is_selected(self) -> bool:
        return self.isSelected()

    def paint(self, painter, option, widget=None):
        """
        Painting is mostly handled by the specific widget types (e.g., button, bar).
        The base class implements common behavior such as selection highlighting.

        :param painter: QPainter object used for drawing the widget.
        :param option: QStyleOptionGraphicsItem containing style options for the widget (e.g., state, level of detail).
        :param widget: Optional QWidget that is being painted on; can be None if not applicable.
        """
        if self.is_selected:
            # Draw a selection rectangle around the widget when selected
            selection_color = QtGui.QColor(0, 120, 215, 100)  # Semi-transparent blue
            selection_pen = QtGui.QPen(selection_color, 2, QtCore.Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
