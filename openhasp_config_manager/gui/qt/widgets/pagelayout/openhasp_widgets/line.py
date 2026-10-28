from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.line_points import bounds, parse_points
from openhasp_config_manager.gui.domain.problems import geometry_value
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import SELECTION_MARGIN, EditableWidget

_DEFAULT_LINE_WIDTH = 3
# measured on a plate: without a `line_color` the line is not visible on the black background
_DEFAULT_LINE_COLOR = "#000000"


class HaspLineItem(EditableWidget):
    """
    A line through `points` (relative to x and y). With `auto_size` (the default) the object is as large as the line;
    `y_invert` flips the line vertically.
    See https://www.openhasp.com/0.7.0/design/objects/line/
    """

    @property
    def points(self):
        return parse_points(self.obj_data.get("points"))

    @property
    def auto_size(self) -> bool:
        return str(self.obj_data.get("auto_size", True)).lower() not in ("false", "0")

    @property
    def obj_w(self) -> int:
        return bounds(self.points)[0] if self.auto_size else geometry_value(self.obj_data, "w")

    @property
    def obj_h(self) -> int:
        return bounds(self.points)[1] if self.auto_size else geometry_value(self.obj_data, "h")

    def boundingRect(self) -> QtCore.QRectF:
        # the line is wider than the object by its width
        margin = number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH) / 2 + SELECTION_MARGIN
        return self.obj_rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        points = self.points
        if self.obj_data.get("y_invert") in (True, 1, "true", "1"):
            top = bounds(points)[1] if self.auto_size else self.obj_h
            points = [(x, top - y) for x, y in points]
        pen = QtGui.QPen(
            to_color(self.style("line_color"), _DEFAULT_LINE_COLOR),
            number(self.style("line_width", _DEFAULT_LINE_WIDTH), _DEFAULT_LINE_WIDTH),
        )
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap if self.style("line_rounded") else QtCore.Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
        super().paint(painter, option, widget)
