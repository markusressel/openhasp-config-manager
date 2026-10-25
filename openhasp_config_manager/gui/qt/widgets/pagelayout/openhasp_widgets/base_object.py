from PyQt6 import QtGui

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import DEFAULT_TRACK, number, to_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_RADIUS = 4


class HaspBaseObjectItem(EditableWidget):
    """
    The base object (`obj`): a rounded rectangle with a border. Used as the background of other objects; `click` 0 lets touches
    go through to the objects below.
    See https://www.openhasp.com/0.7.0/design/objects/obj/
    """

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        radius = number(self.style("radius", _DEFAULT_RADIUS), _DEFAULT_RADIUS)
        border_width = number(self.style("border_width", 1), 1)
        painter.setBrush(to_color(self.style("bg_color"), DEFAULT_TRACK))
        if border_width > 0:
            painter.setPen(QtGui.QPen(to_color(self.style("border_color"), "#808080"), border_width))
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 0)))
        painter.drawRoundedRect(self.obj_rect, radius, radius)
        super().paint(painter, option, widget)
