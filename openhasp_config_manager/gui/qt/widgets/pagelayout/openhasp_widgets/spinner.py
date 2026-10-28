from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_ANGLE = 60
# how long one turn takes (`speed`, in milliseconds) and how often the preview draws the next step of it
_DEFAULT_SPEED = 1000
_FRAME_INTERVAL = 33
# the segment speeds up and slows down on every turn, like the ease in-out of LVGL
_EASING = QtCore.QEasingCurve(QtCore.QEasingCurve.Type.BezierSpline)
_EASING.addCubicBezierSegment(QtCore.QPointF(0.42, 0.0), QtCore.QPointF(0.58, 1.0), QtCore.QPointF(1.0, 1.0))
# measured on a plate: a thin dark ring with a thick blue segment, and no background unless `bg_opa` says so
_DEFAULT_RING_WIDTH = 1
_DEFAULT_SEGMENT_WIDTH = 10
_DEFAULT_RING_COLOR = "#202020"
_DEFAULT_SEGMENT_COLOR = "#00B6FF"
_MAIN_DEFAULTS = {"bg_color": "#FFFFFF", "bg_grad_color": "#202839", "bg_grad_dir": 1}


class HaspSpinnerItem(EditableWidget):
    """
    A ring with a segment of `angle` degrees that turns once every `speed` milliseconds, starting at the top.
    `line_width` and `line_color` are the ring (the main part), `line_width10` and `line_color10` the segment (the indicator).
    See https://www.openhasp.com/0.7.0/design/objects/spinner/
    """

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data, parent_widget)
        self._clock = QtCore.QElapsedTimer()
        self._clock.start()
        self.startTimer(_FRAME_INTERVAL)

    def timerEvent(self, event):
        if self.scene() is not None and self.isVisible():
            self.update()

    @property
    def rotation_degrees(self) -> float:
        """:return: how far the segment has turned from the top in this turn (0 to 360), clockwise unless the direction says otherwise"""
        speed = max(number(self.obj_data.get("speed"), _DEFAULT_SPEED), 1)
        return 360 * _EASING.valueForProgress((self._clock.elapsed() % speed) / speed)

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
        # the segment starts centered at the top (12 o'clock); Qt counts counter-clockwise from 3 o'clock
        center = 90 - direction * self.rotation_degrees
        painter.drawArc(segment, int((center + direction * angle / 2) * 16), int(-direction * angle * 16))
        painter.restore()
        super().paint(painter, option, widget)
