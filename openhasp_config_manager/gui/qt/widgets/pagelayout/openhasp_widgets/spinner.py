from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ANGLE = 60
# measured on a plate: a thin dark ring with a thick blue segment, and no background unless `bg_opa` says so
_DEFAULT_RING_WIDTH = 1
_DEFAULT_SEGMENT_WIDTH = 10
_DEFAULT_RING_COLOR = "#202020"
_DEFAULT_SEGMENT_COLOR = "#00B6FF"
_MAIN_DEFAULTS = {"bg_color": "#FFFFFF", "bg_grad_color": "#202839", "bg_grad_dir": 1}


class HaspSpinnerItem(EditableWidget):
    """
    A ring with a segment of `angle` degrees. The preview does not spin: the segment stays at the top.
    `line_width` and `line_color` are the ring (the main part), `line_width10` and `line_color10` the segment (the indicator).
    See https://www.openhasp.com/0.7.0/design/objects/spinner/
    """

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, defaults=_MAIN_DEFAULTS))

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        ring_width = number(self.style("line_width", _DEFAULT_RING_WIDTH), _DEFAULT_RING_WIDTH)
        segment_width = number(self.style("line_width", _DEFAULT_SEGMENT_WIDTH, Part.INDICATOR), _DEFAULT_SEGMENT_WIDTH)
        side = min(self.obj_w, self.obj_h)
        circle = QtCore.QRectF((self.obj_w - side) / 2, (self.obj_h - side) / 2, side, side)

        # both are as far out as their width allows
        ring = circle.adjusted(ring_width / 2, ring_width / 2, -ring_width / 2, -ring_width / 2)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(to_color(self.style("line_color"), _DEFAULT_RING_COLOR), ring_width))
        painter.drawEllipse(ring)

        angle = number(self.obj_data.get("angle"), _DEFAULT_ANGLE)
        direction = -1 if int(number(self.obj_data.get("direction"), 0)) == 1 else 1
        pen = QtGui.QPen(
            to_color(self.style("line_color", _DEFAULT_SEGMENT_COLOR, Part.INDICATOR), _DEFAULT_SEGMENT_COLOR), segment_width
        )
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        segment = circle.adjusted(segment_width / 2, segment_width / 2, -segment_width / 2, -segment_width / 2)
        # the segment is centered at the top (12 o'clock); Qt counts counter-clockwise from 3 o'clock
        painter.drawArc(segment, int((90 + direction * angle / 2) * 16), int(-direction * angle * 16))
        painter.restore()
        super().paint(painter, option, widget)
