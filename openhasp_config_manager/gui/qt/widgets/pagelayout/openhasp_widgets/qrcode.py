from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.qr_code import qr_modules
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

_DEFAULT_SIZE = 140
_QUIET_ZONE = 4


class HaspQrCodeItem(EditableWidget):
    """
    A square QR code of `size` pixels (`w` and `h` are ignored) with the code of `text`.
    See https://www.openhasp.com/0.7.0/design/objects/qrcode/
    """

    @property
    def obj_w(self) -> int:
        return int(number(self.obj_data.get("size"), _DEFAULT_SIZE))

    @property
    def obj_h(self) -> int:
        return self.obj_w

    def paint(self, painter, option, widget=None):
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("white"))
        painter.drawRect(self.obj_rect)
        rows = qr_modules(str(self.obj_data.get("text", "")))
        module = self.obj_w / ((len(rows) or 1) + 2 * _QUIET_ZONE)
        painter.setBrush(QtGui.QColor("black"))
        for row, line in enumerate(rows):
            for col, dark in enumerate(line):
                if dark:
                    painter.drawRect(QtCore.QRectF((col + _QUIET_ZONE) * module, (row + _QUIET_ZONE) * module, module, module))
        super().paint(painter, option, widget)
