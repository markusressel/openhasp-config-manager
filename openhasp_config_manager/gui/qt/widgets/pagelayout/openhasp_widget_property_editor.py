from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents


class OpenHASPWidgetPropertyEditor(QWidget):
    propertyChanged = QtCore.pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_layout()

    def _create_layout(self):
        self.layout = UiComponents.create_column(parent=self)
