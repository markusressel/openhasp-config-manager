from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TRACK,
    number,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ANGLE = 60
_DEFAULT_LINE_WIDTH = 20


class HaspSpinnerItem(EditableWidget):
    """
    A ring with a segment of `angle` degrees. The preview does not spin: the segment stays at the top.
    `line_width` and `line_color` are the ring (the main part), `line_width10` and `line_color10` the segment (the indicator).
    See https://www.openhasp.com/0.7.0/design/objects/spinner/
    """

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        ring_width = number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH)
        segment_width = number(self.style("line_width", ring_width, Part.INDICATOR), ring_width)
        side = min(self.obj_w, self.obj_h)
        inset = max(ring_width, segment_width) / 2
        rect = QtCore.QRectF((self.obj_w - side) / 2, (self.obj_h - side) / 2, side, side).adjusted(
            inset, inset, -inset, -inset
        )

        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(to_color(self.style("line_color"), DEFAULT_TRACK), ring_width))
        painter.drawEllipse(rect)

        angle = number(self.obj_data.get("angle"), _DEFAULT_ANGLE)
        direction = -1 if int(number(self.obj_data.get("direction"), 0)) == 1 else 1
        pen = QtGui.QPen(to_color(self.style("line_color", DEFAULT_ACCENT, Part.INDICATOR), DEFAULT_ACCENT), segment_width)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # the segment is centered at the top (12 o'clock); Qt counts counter-clockwise from 3 o'clock
        painter.drawArc(rect, int((90 + direction * angle / 2) * 16), int(-direction * angle * 16))
        super().paint(painter, option, widget)
