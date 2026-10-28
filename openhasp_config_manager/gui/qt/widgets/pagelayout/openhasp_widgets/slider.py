from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import HaspBarItem, indicator_rect
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INDICATOR_DEFAULTS,
    KNOB_DEFAULTS,
    SLIDER_KNOB_PADDING,
    TRACK_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import fraction


class HaspSliderItem(HaspBarItem):
    """A bar with a knob (part 2) at the end of the indicator: a square as big as the slider is thick, plus its padding."""

    # Signal to notify when the value changes via mouse interaction
    valueChanged = QtCore.pyqtSignal(int, int)  # (object_id, new_value)

    @property
    def min_val(self) -> int:
        return self.obj_data.get("min", 0)

    @property
    def max_val(self) -> int:
        return self.obj_data.get("max", 100)

    @property
    def val(self) -> int:
        return self.obj_data.get("val", 0)

    @property
    def progress(self) -> float:
        return fraction(self._val, self.min_val, self.max_val)

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data, parent_widget)

        self._val = self.val  # Internal value to track changes

        # Native OpenHASP coordinates
        self.setPos(self.obj_x, self.obj_y)

        # Interactivity
        self.setAcceptHoverEvents(True)

    def _knob_rect(self) -> QtCore.QRectF:
        inner = self.inner_rect()
        left, top, right, bottom = padding(self, Part.KNOB, SLIDER_KNOB_PADDING)
        thickness = min(self.obj_w, self.obj_h)
        width, height = thickness + left + right, thickness + top + bottom
        if self.is_vertical:
            center = QtCore.QPointF(self.obj_w / 2, inner.bottom() - inner.height() * self.progress)
        else:
            center = QtCore.QPointF(inner.left() + inner.width() * self.progress, self.obj_h / 2)
        return QtCore.QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    def boundingRect(self) -> QtCore.QRectF:
        """The knob reaches over the track."""
        return super().boundingRect().united(self._knob_rect().adjusted(-3, -3, 3, 3))

    def _on_data_changed(self):
        self._val = self.val

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        if self.progress > 0:
            draw_box(
                painter,
                indicator_rect(self.inner_rect(), self.progress, self.is_vertical),
                box_style(self, Part.INDICATOR, INDICATOR_DEFAULTS),
            )

        draw_box(painter, self._knob_rect(), box_style(self, Part.KNOB, KNOB_DEFAULTS))

        # selection outline of the base class
        super(HaspBarItem, self).paint(painter, option, widget)

    # --- Interaction Logic ---

    def mousePressEvent(self, event):
        self._update_value_from_pos(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._update_value_from_pos(event.pos())
        super().mouseMoveEvent(event)

    def _update_value_from_pos(self, local_pos):
        """Calculates value based on where the mouse is on the track."""
        inner = self.inner_rect()
        if self.is_vertical:
            pct = (inner.bottom() - local_pos.y()) / inner.height() if inner.height() > 0 else 0
        else:
            pct = (local_pos.x() - inner.left()) / inner.width() if inner.width() > 0 else 0
        pct = max(0.0, min(pct, 1.0))

        new_val = int(self.min_val + (pct * (self.max_val - self.min_val)))

        if new_val != self._val:
            self._val = new_val
            self.update()  # Triggers repaint
            self.valueChanged.emit(self.obj_id, self._val)
