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

        # Initial sync: Move the item to the position defined in the JSON data
        self.setPos(float(self.obj_x), float(self.obj_y))

    @property
    def live_x(self) -> int:
        """The current X position in the scene (after user drag)."""
        return int(self.pos().x())

    @property
    def live_y(self) -> int:
        """The current Y position in the scene (after user drag)."""
        return int(self.pos().y())

    @property
    def delta_x(self) -> int:
        """How far the widget has moved from its original data point."""
        return self.live_x - self.obj_x

    @property
    def delta_y(self) -> int:
        """How far the widget has moved from its original data point."""
        return self.live_y - self.obj_y

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # This is called WHENEVER the item is moved (dragging or setPos)
            # 'value' is the new QPointF the item is moving to.
            self.update()

        return super().itemChange(change, value)

    @property
    def is_selected(self) -> bool:
        return self.isSelected()

    def boundingRect(self) -> QtCore.QRectF:
        # Get the base dimensions
        rect = self.obj_rect

        # Increase the rect by the pen width of the selection-outline to prevent smearing
        margin = 3
        return rect.adjusted(-margin, -margin, margin, margin)

    @property
    def obj_rect(self):
        return QtCore.QRectF(0, 0, self.obj_w, self.obj_h)

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
            selection_color = QtGui.QColor("red")  # Semi-transparent blue
            selection_pen = QtGui.QPen(selection_color, 2, QtCore.Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

            # CRITICAL: Do NOT use self.boundingRect() here.
            # Use the actual dimensions of the widget.
            # This ensures the drawing is well within the 3px margin.
            widget_rect = self.obj_rect
            painter.drawRect(widget_rect)
