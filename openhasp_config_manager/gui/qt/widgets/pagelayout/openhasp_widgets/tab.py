from PyQt6 import QtCore

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspTabItem(EditableWidget):
    """
    A tab of a tabview (`parentid`). It has no place of its own: the tabview draws its button, so the preview draws nothing
    for it. Select it in the text editor.
    See https://www.openhasp.com/0.7.0/design/objects/tabview/
    """

    @property
    def obj_w(self) -> int:
        return 0

    @property
    def obj_h(self) -> int:
        return 0

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF()

    def paint(self, painter, option, widget=None):
        pass
