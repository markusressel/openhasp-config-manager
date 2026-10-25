from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.style_parts import Part

from openhasp_config_manager.gui.domain.button_matrix import matrix_rows
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_ACCENT,
    DEFAULT_TEXT,
    DEFAULT_TRACK,
    draw_text,
    number,
    plate_font,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_GAP = 4


class HaspButtonMatrixItem(EditableWidget):
    """
    Rows of buttons from `options` (`"\\n"` starts a new row, `#RRGGBB text#` colors a label). Every row has the same height and
    the buttons of a row share its width. The button `val` is drawn as checked if the buttons toggle.
    See https://www.openhasp.com/0.7.0/design/objects/btnmatrix/
    """

    def button_rects(self):
        """:return: the rect of every button with its MatrixButton, in the order of `options`"""
        rows = matrix_rows(self.obj_data.get("options", "Text"))
        result = []
        for row_index, row in enumerate(rows):
            height = (self.obj_h - _GAP * (len(rows) - 1)) / len(rows)
            width = (self.obj_w - _GAP * (len(row) - 1)) / len(row)
            for column, button in enumerate(row):
                rect = QtCore.QRectF(column * (width + _GAP), row_index * (height + _GAP), width, height)
                result.append((rect, button))
        return result

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        radius = number(self.style("radius", 4), 4)
        toggles = str(self.obj_data.get("toggle", False)).lower() in ("true", "1")
        active = int(number(self.obj_data.get("val"), 0))
        font = plate_font(self.style("text_font", 25))
        for index, (rect, button) in enumerate(self.button_rects()):
            checked = toggles and index == active
            painter.setBrush(
                to_color(
                    self.style("bg_color", DEFAULT_ACCENT if checked else None, Part.ITEMS),
                    DEFAULT_ACCENT if checked else DEFAULT_TRACK,
                )
            )
            painter.setPen(QtGui.QPen(to_color(self.style("border_color"), "#808080"), 1))
            painter.drawRoundedRect(rect, radius, radius)
            color = to_color(button.color or self.style("text_color"), DEFAULT_TEXT)
            draw_text(painter, rect, button.text, color, font, self.obj_data.get("align", "center"))
        super().paint(painter, option, widget)
