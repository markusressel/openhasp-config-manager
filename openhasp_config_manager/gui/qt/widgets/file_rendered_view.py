from PyQt6 import QtCore
from PyQt6.QtWidgets import QFrame, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget

OUT_OF_DATE_TEXT = "Out of date: the editor has unsaved changes. Save the file to render them."


class FileRenderedView(QWidget):
    """
    The rendered JSONL of the file in the current tab (`view`), with a banner above it while the text in the editor is not what
    the view was rendered from: the draft renders saved files only.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = PageJsonlPreviewWidget(sort_objects=False, placeholder="Open a file to see it rendered.")

        column = UiComponents.create_column(parent=self)
        column.setSpacing(0)
        self._banner = QFrame()
        self._banner.setProperty("role", "banner")
        row = UiComponents.create_row(parent=self._banner, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        row.addWidget(UiComponents.create_icon_label("sync-alert"))
        self._text = UiComponents.create_label(OUT_OF_DATE_TEXT, word_wrap=True)
        row.addWidget(self._text, 1)
        self._banner.hide()
        column.addWidget(self._banner)
        column.addWidget(self.view, 1)

    @property
    def out_of_date(self) -> bool:
        return not self._banner.isHidden()

    def set_out_of_date(self, out_of_date: bool):
        self._banner.setVisible(out_of_date)
