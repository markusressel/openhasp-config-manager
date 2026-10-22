from typing import Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene, QApplication

from openhasp_config_manager.gui.domain.snapping import snap_rect, Rect
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

GRID_SIZE = 8
# the distance (in plate pixels) at which a dragged object snaps to an edge or center of another one
ALIGNMENT_THRESHOLD = 6


class PlateScene(QGraphicsScene):
    """
    The scene of the plate preview, in the native resolution of the plate.
    Snaps objects that are dragged by the mouse to alignment guides or the grid.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snap_enabled = True
        self.grid_size = GRID_SIZE
        self.guides_x: Tuple[float, ...] = ()
        self.guides_y: Tuple[float, ...] = ()

    def snap_position(self, item: EditableWidget, position: QPointF) -> QPointF:
        """
        Called by EditableWidget when it moves. Only drags of a single object with the mouse are snapped,
        holding Alt disables snapping.
        """
        dragging = QApplication.mouseButtons() != QtCore.Qt.MouseButton.NoButton
        alt_held = bool(QApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.AltModifier)
        if not self.snap_enabled or not dragging or alt_held or len(self.selectedItems()) != 1:
            self.clear_guides()
            return position

        others = [
            Rect(other.x(), other.y(), other.obj_w, other.obj_h)
            for other in self.items()
            if isinstance(other, EditableWidget) and other is not item
        ]
        bounds = self.sceneRect()
        result = snap_rect(
            rect=Rect(position.x(), position.y(), item.obj_w, item.obj_h),
            others=others,
            bounds=Rect(bounds.x(), bounds.y(), bounds.width(), bounds.height()),
            grid=self.grid_size,
            threshold=ALIGNMENT_THRESHOLD,
        )
        self.guides_x = result.guides_x
        self.guides_y = result.guides_y
        self.update()
        return QPointF(result.x, result.y)

    def clear_guides(self):
        if self.guides_x or self.guides_y:
            self.guides_x = ()
            self.guides_y = ()
            self.update()
