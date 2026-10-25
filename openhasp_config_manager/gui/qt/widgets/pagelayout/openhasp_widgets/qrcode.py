from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.qr_placeholder import MODULES, placeholder_modules
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_SIZE = 140
_QUIET_ZONE = 4


class HaspQrCodeItem(EditableWidget):
    """
    A square QR code of `size` pixels (`w` and `h` are ignored). The preview draws a pattern that looks like a QR code of the
    text, not the code itself, see `qr_placeholder.py`.
    See https://www.openhasp.com/0.7.0/design/objects/qrcode/
    """

    @property
    def obj_w(self) -> int:
        return int(number(self.obj_data.get("size"), _DEFAULT_SIZE))

    @property
    def obj_h(self) -> int:
        return self.obj_w

    def __init__(self, obj_data, parent_widget=None):
        super().__init__(obj_data)
        self.parent_widget = parent_widget

    def paint(self, painter, option, widget=None):
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("white"))
        painter.drawRect(self.obj_rect)
        module = self.obj_w / (MODULES + 2 * _QUIET_ZONE)
        painter.setBrush(QtGui.QColor("black"))
        for row, line in enumerate(placeholder_modules(str(self.obj_data.get("text", "")))):
            for col, dark in enumerate(line):
                if dark:
                    painter.drawRect(QtCore.QRectF((col + _QUIET_ZONE) * module, (row + _QUIET_ZONE) * module, module, module))
        super().paint(painter, option, widget)
