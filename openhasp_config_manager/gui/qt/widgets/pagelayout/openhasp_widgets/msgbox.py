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

_PADDING = 12
_BUTTON_HEIGHT = 36
_GAP = 8


class HaspMessageBoxItem(EditableWidget):
    """
    A pop-up with a `text` and a button for every entry of `options` (`["OK"]` by default). On the plate it is centered and as wide
    as the screen unless it has a size, and goes away when a button is pressed; the preview shows it like any other object.
    See https://www.openhasp.com/0.7.0/design/objects/msgbox/
    """

    def buttons(self):
        options = self.obj_data.get("options", ["OK"])
        return [button.text for row in matrix_rows(options) for button in row]

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        radius = number(self.style("radius", 6), 6)
        painter.setBrush(to_color(self.style("bg_color"), DEFAULT_TRACK))
        painter.setPen(QtGui.QPen(to_color(self.style("border_color"), "#808080"), number(self.style("border_width", 1), 1)))
        painter.drawRoundedRect(self.obj_rect, radius, radius)

        font = plate_font(self.style("text_font", 25))
        text_rect = self.obj_rect.adjusted(_PADDING, _PADDING, -_PADDING, -(_PADDING + _BUTTON_HEIGHT + _GAP))
        painter.setFont(font)
        painter.setPen(to_color(self.style("text_color"), DEFAULT_TEXT))
        painter.drawText(
            text_rect,
            int(QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap),
            str(self.obj_data.get("text", "")),
        )

        buttons = self.buttons()
        if buttons:
            width = (self.obj_w - 2 * _PADDING - _GAP * (len(buttons) - 1)) / len(buttons)
            for index, text in enumerate(buttons):
                rect = QtCore.QRectF(
                    _PADDING + index * (width + _GAP), self.obj_h - _PADDING - _BUTTON_HEIGHT, width, _BUTTON_HEIGHT
                )
                painter.setBrush(to_color(self.style("bg_color", DEFAULT_ACCENT, Part.ITEMS), DEFAULT_ACCENT))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 4, 4)
                draw_text(painter, rect, text, QtGui.QColor(DEFAULT_TEXT), font)
        super().paint(painter, option, widget)
